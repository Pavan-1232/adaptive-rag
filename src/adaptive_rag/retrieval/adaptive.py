"""Adaptive retrieval: per-part search, coverage-first selection, dynamic depth, dedupe and
span merging, diversity, neighbor expansion, all inside a token budget (DESIGN.md section 6).

Every step has its own switch in AdaptiveParams, so each can be measured and turned off.
With splitting, depth, dedupe, merging, diversity, neighbors and hybrid all off, this is
top-max_chunks by score.
"""

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field, replace

from adaptive_rag.chunking.base import count_tokens
from adaptive_rag.config import Settings
from adaptive_rag.context import AppContext
from adaptive_rag.knowledge_bases import check_embedding_lock

from .baseline import load_chunks, load_neighbor, ready_document_ids
from .keyword import exact_hit, keyword_search
from .query import QueryPlan, analyze
from .types import RetrievedChunk

_WORD = re.compile(r"\w+")
DIVERSE_KINDS = ("comparative", "broad")


@dataclass(frozen=True)
class AdaptiveParams:
    budget: int = 2500
    pool_size: int = 30
    split_parts: bool = True
    floor: float = 0.25
    # Stop when a score falls below top - delta. None turns the rule off.
    delta: float | None = 0.15
    # Stop at the largest score gap between min_chunks and the type's maximum.
    gap_cutoff: bool = True
    min_chunks: int = 3
    max_chunks: dict[str, int] = field(
        default_factory=lambda: {
            "factual": 5,
            "table": 5,
            "multi_part": 8,
            "comparative": 10,
            "broad": 10,
        }
    )
    dedupe: bool = True
    dedupe_jaccard: float = 0.9
    # Merge overlapping or adjacent chunks of one document into one block, so shared
    # overlap text is sent (and charged) once.
    merge_spans: bool = True
    # Comparative and broad questions: at most this many direct hits per document while other
    # documents still have candidates. None turns it off.
    doc_cap: int | None = 3
    neighbors: bool = False
    expand_threshold: float = 0.5
    # Share of the budget held back from direct hits for neighbors (design default 30%).
    neighbor_reserve: float = 0.3
    # Hybrid: add FTS5 keyword hits to each pool and rank by cosine + weight * BM25 strength.
    hybrid: bool = False
    keyword_weight: float = 0.1
    keyword_pool: int = 10
    keyword_query: str = "words"  # "words" | "phrases" (keyword.match_query)
    # "weighted": rank by cosine + keyword_weight * strength. "rrf": rank-based fusion, and
    # keyword hits ranked <= strong_keyword_rank go in first, past the floor and the gap cut.
    fusion: str = "weighted"
    rrf_k: int = 60
    strong_keyword_rank: int = 2
    # Weighted hybrid: the best numeric-phrase match goes in first (at most one chunk).
    keyword_bypass: bool = False

    @classmethod
    def from_settings(cls, settings: Settings, embedding_model: str) -> "AdaptiveParams":
        return cls(
            budget=settings.evidence_target_tokens,
            split_parts=settings.adaptive_split_parts,
            floor=settings.depth_floor_for(embedding_model),
            delta=settings.adaptive_delta,
            gap_cutoff=settings.adaptive_gap_cutoff,
            min_chunks=settings.adaptive_min_chunks,
            max_chunks=dict(settings.adaptive_max_chunks),
            dedupe=settings.adaptive_dedupe,
            dedupe_jaccard=settings.adaptive_dedupe_jaccard,
            merge_spans=settings.adaptive_merge_spans,
            doc_cap=settings.adaptive_doc_cap,
            neighbors=settings.adaptive_neighbors,
            expand_threshold=settings.adaptive_expand_threshold,
            neighbor_reserve=settings.adaptive_neighbor_reserve,
            hybrid=settings.adaptive_hybrid,
            keyword_weight=settings.adaptive_keyword_weight,
            keyword_pool=settings.adaptive_keyword_pool,
            keyword_query=settings.adaptive_keyword_query,
            fusion=settings.adaptive_fusion,
            rrf_k=settings.adaptive_rrf_k,
            strong_keyword_rank=settings.adaptive_strong_keyword_rank,
            keyword_bypass=settings.adaptive_keyword_bypass,
        )


@dataclass
class AdaptiveRetrieval:
    plan: QueryPlan
    chunks: list[RetrievedChunk]  # what the model reads, in prompt order (blocks when merged)
    candidates: list[RetrievedChunk]  # the scored pool, best first, for traces and metrics
    part_top_scores: list[float]
    uncovered_parts: list[str]
    duplicates_dropped: int = 0
    duplicate_tokens: int = 0
    stop_reason: str = ""
    merged_tokens_saved: int = 0

    @property
    def tokens(self) -> int:
        return sum(chunk.evidence_tokens for chunk in self.chunks)


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 1.0


# ---------------------------------------------------------------- blocks


def _best_direct(group: list[RetrievedChunk]) -> float:
    direct = [c.score for c in group if c.source == "direct"]
    return max(direct or [c.score for c in group])


def _groups(chunks: list[RetrievedChunk]) -> list[list[RetrievedChunk]]:
    """Chunks of one document that overlap or are consecutive, in document order. Groups are
    ordered by their best direct score."""
    by_document: dict[int, list[RetrievedChunk]] = defaultdict(list)
    for chunk in chunks:
        by_document[chunk.document_id].append(chunk)
    groups: list[list[RetrievedChunk]] = []
    for members in by_document.values():
        members.sort(key=lambda c: (c.chunk_index, c.start_char))
        current = [members[0]]
        for chunk in members[1:]:
            reach = max(c.end_char for c in current)
            if chunk.chunk_index == current[-1].chunk_index + 1 or chunk.start_char < reach:
                current.append(chunk)
            else:
                groups.append(current)
                current = [chunk]
        groups.append(current)
    groups.sort(key=lambda g: -_best_direct(g))  # stable: ties keep document order
    return groups


def merge_block(group: list[RetrievedChunk]) -> RetrievedChunk:
    """One evidence block from adjacent chunks. Chunk text is canonical_text[start:end], so
    overlap is cut by character offset and the shared text appears once."""
    if len(group) == 1:
        return group[0]
    text, end = group[0].text, group[0].end_char
    for chunk in group[1:]:
        if chunk.start_char <= end:
            text += chunk.text[end - chunk.start_char :] if chunk.end_char > end else ""
        else:
            # shortcut: the gap between non-touching chunks isn't stored; joined with a newline.
            text += "\n" + chunk.text
        end = max(end, chunk.end_char)
    direct = [c for c in group if c.source == "direct"]
    # shortcut: later members' C7 header context is dropped; the first member's is kept.
    return replace(
        group[0],
        text=text,
        token_count=count_tokens(text),
        end_char=end,
        locator_start=min(c.locator_start for c in group),
        locator_end=max(c.locator_end for c in group),
        score=_best_direct(group),
        keyword=max(c.keyword for c in group),
        source="direct" if direct else "expansion",
        members=tuple(group),
    )


def assemble(chunks: list[RetrievedChunk], merge: bool) -> list[RetrievedChunk]:
    """Prompt order: blocks by best direct score, document order inside a block."""
    groups = _groups(chunks) if chunks else []
    if merge:
        return [merge_block(group) for group in groups]
    return [chunk for group in groups for chunk in group]


def _cost(chunks: list[RetrievedChunk], merge: bool) -> int:
    if not merge:
        return sum(c.evidence_tokens for c in chunks)
    return sum(b.evidence_tokens for b in assemble(chunks, True))


# ---------------------------------------------------------------- selection


def _gap_cut(eligible: list[RetrievedChunk], params: AdaptiveParams, limit: int, rank):
    """The chunk just after the largest score drop between positions min_chunks and limit."""
    start = max(params.min_chunks, 1)
    stop = min(limit, len(eligible) - 1)
    if stop < start:
        return None
    position = max(range(start, stop + 1), key=lambda i: rank(eligible[i - 1]) - rank(eligible[i]))
    return eligible[position].chunk_id


def ranking(pools: list[list[RetrievedChunk]], params: AdaptiveParams):
    """The ranking function, and the chunk ids of strong keyword hits (RRF only).
    RRF ranks within each pool (the full question, then each part); a chunk keeps its best."""
    if not params.hybrid:
        return (lambda c: c.score), set()
    if params.fusion == "weighted":
        bypass = (
            {c.chunk_id for c in pools[0] if c.exact} if params.keyword_bypass and pools else set()
        )
        return (lambda c: c.score + params.keyword_weight * c.keyword), bypass
    if params.fusion != "rrf":
        raise ValueError(f"unknown fusion: {params.fusion}")
    fused: dict[str, float] = {}
    strong: set[str] = set()
    for pool in pools:
        by_vector = sorted(pool, key=lambda c: (-c.score, c.chunk_id))
        by_keyword = sorted(
            (c for c in pool if c.keyword > 0), key=lambda c: (-c.keyword, c.chunk_id)
        )
        keyword_rank = {c.chunk_id: i + 1 for i, c in enumerate(by_keyword)}
        for i, chunk in enumerate(by_vector):
            value = 1 / (params.rrf_k + i + 1)
            if chunk.chunk_id in keyword_rank:
                value += 1 / (params.rrf_k + keyword_rank[chunk.chunk_id])
                if keyword_rank[chunk.chunk_id] <= params.strong_keyword_rank:
                    strong.add(chunk.chunk_id)
            fused[chunk.chunk_id] = max(fused.get(chunk.chunk_id, 0.0), value)
    return (lambda c: fused[c.chunk_id]), strong


def select(
    plan: QueryPlan,
    pools: list[list[RetrievedChunk]],
    params: AdaptiveParams,
) -> tuple[list[RetrievedChunk], dict]:
    """Choose direct hits from per-query pools. pools[0] is the full question; pools[1:] are
    the parts, when the question was split. Pure function, so the rules are unit-tested.
    Floors use cosine score. Weighted hybrid: ranking, delta and gap use score + keyword
    weight. RRF: ranking and gap use the fused rank, delta stays on cosine (its tuned scale),
    and strong keyword hits go in first, past the floor and the gap cut."""
    rank, strong = ranking(pools, params)
    rrf = params.hybrid and params.fusion == "rrf"

    def level(chunk: RetrievedChunk) -> float:  # what the delta cut-off compares
        return chunk.score if rrf else rank(chunk)

    def below_floor_(chunk: RetrievedChunk) -> bool:
        return chunk.score < params.floor and chunk.chunk_id not in strong

    best: dict[str, RetrievedChunk] = {}
    for pool in pools:
        for chunk in pool:
            if chunk.chunk_id not in best or rank(chunk) > rank(best[chunk.chunk_id]):
                best[chunk.chunk_id] = chunk
    ranked = sorted(best.values(), key=lambda c: (-rank(c), c.chunk_id))
    limit = params.max_chunks.get(plan.kind, 5)
    direct_budget = (
        int(params.budget * (1 - params.neighbor_reserve)) if params.neighbors else params.budget
    )

    chosen: list[RetrievedChunk] = []
    chosen_words: list[set[str]] = []
    stats = {
        "duplicates_dropped": 0,
        "duplicate_tokens": 0,
        "stop_reason": "pool exhausted",
        "capped": 0,
    }

    def try_add(chunk: RetrievedChunk) -> str:
        if any(c.chunk_id == chunk.chunk_id for c in chosen):
            return "chosen"
        words = _words(chunk.text)
        if params.dedupe and any(_jaccard(words, w) >= params.dedupe_jaccard for w in chosen_words):
            stats["duplicates_dropped"] += 1
            stats["duplicate_tokens"] += chunk.evidence_tokens
            return "duplicate"
        if _cost([*chosen, chunk], params.merge_spans) > direct_budget:
            return "budget"
        chosen.append(chunk)
        chosen_words.append(words)
        return "added"

    # Strong keyword hits first (RRF only): an exact-term match the vectors rank low.
    for chunk in ranked:
        if chunk.chunk_id in strong and len(chosen) < limit:
            try_add(chunk)

    # Coverage first: the best chunk for each part, if it clears the floor.
    for pool in pools[1:]:
        for chunk in sorted(pool, key=lambda c: -rank(c)):
            if below_floor_(chunk):
                continue
            if try_add(best[chunk.chunk_id]) in ("added", "chosen"):
                break

    eligible = [c for c in ranked if not below_floor_(c)]
    gap_cut = _gap_cut(eligible, params, limit, rank) if params.gap_cutoff else None
    capped = params.doc_cap is not None and plan.kind in DIVERSE_KINDS
    deferred: list[RetrievedChunk] = []
    top = max((level(c) for c in ranked), default=0.0)
    below_floor = False
    for chunk in ranked:
        if len(chosen) >= limit:
            stats["stop_reason"] = "max chunks"
            break
        if below_floor_(chunk):
            below_floor = True  # with hybrid, a later chunk can still clear the floor
            continue
        if len(chosen) >= params.min_chunks:
            if params.delta is not None and level(chunk) < top - params.delta:
                stats["stop_reason"] = "delta"
                break
            if chunk.chunk_id == gap_cut:
                stats["stop_reason"] = "gap"
                break
        if capped and chunk not in chosen:
            same_document = sum(c.document_id == chunk.document_id for c in chosen)
            if same_document >= params.doc_cap:
                deferred.append(chunk)
                continue
        if try_add(chunk) == "budget":
            stats["stop_reason"] = "budget"
            break
    else:
        if below_floor:
            stats["stop_reason"] = "floor"

    # The cap is soft: when other documents run out, capped chunks fill the remaining room.
    for chunk in deferred:
        if len(chosen) >= limit or try_add(chunk) == "budget":
            break
    stats["capped"] = sum(c not in chosen for c in deferred)
    return chosen, stats


def expand(
    direct: list[RetrievedChunk], params: AdaptiveParams, neighbor_of
) -> list[RetrievedChunk]:
    """Add the chunks before and after strong direct hits, same document and section only,
    within the budget, then assemble blocks. Neighbors use the reserve plus any room the
    direct hits left."""
    selected = list(direct)
    if params.neighbors:
        taken = {(c.document_id, c.chunk_index) for c in direct}
        for hit in sorted(direct, key=lambda c: -c.score):
            if hit.score < params.expand_threshold:
                continue
            for index in (hit.chunk_index - 1, hit.chunk_index + 1):
                if (hit.document_id, index) in taken or index < 0:
                    continue
                neighbor = neighbor_of(hit.document_id, index, hit.score)
                if neighbor is None or neighbor.document_id != hit.document_id:
                    continue
                if (
                    hit.section_heading is not None
                    and neighbor.section_heading is not None
                    and neighbor.section_heading != hit.section_heading
                ):
                    continue
                if _cost([*selected, neighbor], params.merge_spans) > params.budget:
                    continue
                selected.append(neighbor)
                taken.add((hit.document_id, index))
    return assemble(selected, params.merge_spans)


def uncovered_parts(
    plan: QueryPlan,
    pools: list[list[RetrievedChunk]],
    sent: list[RetrievedChunk],
    floor: float,
) -> list[str]:
    """Parts with no chunk above the floor among the evidence actually sent. A part whose
    best chunk was dropped for budget is uncovered, even though search found it."""
    sent_ids = {piece.chunk_id for chunk in sent for piece in chunk.pieces}
    part_pools = pools[1:] if len(pools) > 1 else pools
    return [
        part
        for part, pool in zip(plan.parts, part_pools, strict=True)
        if not any(c.chunk_id in sent_ids and c.score >= floor for c in pool)
    ]


def _pool(ctx: AppContext, kb, text: str, params: AdaptiveParams, document_ids: list[int]):
    embedding = ctx.embedder.embed_query(text)
    hits = ctx.store.query(kb["collection_name"], embedding, params.pool_size, document_ids)
    scored = [(h.chunk_id, h.score) for h in hits]
    if not params.hybrid:
        return load_chunks(ctx, scored)
    strength = dict(
        keyword_search(ctx, text, params.keyword_pool, document_ids, params.keyword_query)
    )
    exact = exact_hit(ctx, text, document_ids) if params.keyword_bypass else None
    known = {chunk_id for chunk_id, _ in scored}
    missing = [c for c in dict.fromkeys([*strength, exact]) if c is not None and c not in known]
    cosine = ctx.store.similarity(kb["collection_name"], embedding, missing)
    scored += [(chunk_id, cosine[chunk_id]) for chunk_id in missing if chunk_id in cosine]
    return [
        replace(c, keyword=strength.get(c.chunk_id, 0.0), exact=c.chunk_id == exact)
        for c in load_chunks(ctx, scored)
    ]


def retrieve_adaptive(
    ctx: AppContext, kb: sqlite3.Row, question: str, params: AdaptiveParams
) -> AdaptiveRetrieval:
    check_embedding_lock(ctx, kb)
    plan = analyze(question, split=params.split_parts)
    document_ids = ready_document_ids(ctx, kb)
    if not document_ids:
        return AdaptiveRetrieval(plan, [], [], [], list(plan.parts))

    queries = [question] + (list(plan.parts) if len(plan.parts) > 1 else [])
    pools = [_pool(ctx, kb, text, params, document_ids) for text in queries]
    direct, stats = select(plan, pools, params)
    chunks = expand(
        direct,
        params,
        lambda document_id, index, score: load_neighbor(ctx, document_id, index, score),
    )

    part_pools = pools[1:] if len(pools) > 1 else pools
    part_top = [max((c.score for c in pool), default=0.0) for pool in part_pools]
    merged: dict[str, RetrievedChunk] = {}
    for pool in pools:
        for chunk in pool:
            if chunk.chunk_id not in merged or chunk.score > merged[chunk.chunk_id].score:
                merged[chunk.chunk_id] = chunk
    rank, _ = ranking(pools, params)
    # Cosine order, as before, except with RRF, where the fused order is what was used.
    if params.hybrid and params.fusion == "rrf":
        candidates = sorted(merged.values(), key=lambda c: (-rank(c), c.chunk_id))
    else:
        candidates = sorted(merged.values(), key=lambda c: (-c.score, c.chunk_id))
    saved = sum(p.evidence_tokens for c in chunks for p in c.pieces) - sum(
        c.evidence_tokens for c in chunks
    )
    return AdaptiveRetrieval(
        plan,
        chunks,
        candidates,
        part_top,
        uncovered_parts(plan, pools, chunks, params.floor),
        stats["duplicates_dropped"],
        stats["duplicate_tokens"],
        stats["stop_reason"],
        saved,
    )
