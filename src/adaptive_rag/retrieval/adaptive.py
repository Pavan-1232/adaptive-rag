"""Adaptive retrieval: per-part search, coverage-first selection, dynamic depth, dedupe,
neighbor expansion, all inside a token budget (DESIGN.md section 6).

Every step has its own switch in AdaptiveParams, so each can be measured and turned off.
With splitting, depth, dedupe and neighbors all off, this is top-max_chunks by score.
"""

import re
import sqlite3
from dataclasses import dataclass, field

from adaptive_rag.config import Settings
from adaptive_rag.context import AppContext
from adaptive_rag.knowledge_bases import check_embedding_lock

from .baseline import load_chunks, load_neighbor, ready_document_ids
from .query import QueryPlan, analyze
from .types import RetrievedChunk

_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class AdaptiveParams:
    budget: int = 2500
    pool_size: int = 30
    split_parts: bool = True
    floor: float = 0.25
    # Stop when a score falls below top - delta. None turns the rule off.
    delta: float | None = 0.15
    min_chunks: int = 3
    max_chunks: dict[str, int] = field(
        default_factory=lambda: {"factual": 5, "table": 5, "multi_part": 8, "broad": 10}
    )
    dedupe: bool = True
    dedupe_jaccard: float = 0.9
    neighbors: bool = False
    expand_threshold: float = 0.5
    # Share of the budget held back for neighbors. 0 means neighbors use only what's left.
    neighbor_reserve: float = 0.0

    @classmethod
    def from_settings(cls, settings: Settings, embedding_model: str) -> "AdaptiveParams":
        return cls(
            budget=settings.evidence_target_tokens,
            split_parts=settings.adaptive_split_parts,
            floor=settings.depth_floor_for(embedding_model),
            delta=settings.adaptive_delta,
            min_chunks=settings.adaptive_min_chunks,
            max_chunks=dict(settings.adaptive_max_chunks),
            dedupe=settings.adaptive_dedupe,
            dedupe_jaccard=settings.adaptive_dedupe_jaccard,
            neighbors=settings.adaptive_neighbors,
            expand_threshold=settings.adaptive_expand_threshold,
            neighbor_reserve=settings.adaptive_neighbor_reserve,
        )


@dataclass
class AdaptiveRetrieval:
    plan: QueryPlan
    chunks: list[RetrievedChunk]  # what the model reads, in prompt order
    candidates: list[RetrievedChunk]  # the scored pool, best first, for traces and metrics
    part_top_scores: list[float]
    uncovered_parts: list[str]
    duplicates_dropped: int = 0
    duplicate_tokens: int = 0
    stop_reason: str = ""

    @property
    def tokens(self) -> int:
        return sum(chunk.evidence_tokens for chunk in self.chunks)


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a or b else 1.0


def _search(ctx: AppContext, kb, text: str, n: int, document_ids: list[int]):
    embedding = ctx.embedder.embed_query(text)
    return [
        (h.chunk_id, h.score)
        for h in ctx.store.query(kb["collection_name"], embedding, n, document_ids)
    ]


def select(
    plan: QueryPlan,
    pools: list[list[RetrievedChunk]],
    params: AdaptiveParams,
) -> tuple[list[RetrievedChunk], dict]:
    """Choose direct hits from per-query pools. pools[0] is the full question; pools[1:] are
    the parts, when the question was split. Pure function, so the rules are unit-tested."""
    best: dict[str, RetrievedChunk] = {}
    for pool in pools:
        for chunk in pool:
            if chunk.chunk_id not in best or chunk.score > best[chunk.chunk_id].score:
                best[chunk.chunk_id] = chunk
    ranked = sorted(best.values(), key=lambda c: (-c.score, c.chunk_id))
    limit = params.max_chunks.get(plan.kind, 5)
    direct_budget = (
        int(params.budget * (1 - params.neighbor_reserve)) if params.neighbors else (params.budget)
    )

    chosen: list[RetrievedChunk] = []
    chosen_words: list[set[str]] = []
    used = 0
    stats = {"duplicates_dropped": 0, "duplicate_tokens": 0, "stop_reason": "pool exhausted"}

    def try_add(chunk: RetrievedChunk) -> bool:
        nonlocal used
        if any(c.chunk_id == chunk.chunk_id for c in chosen):
            return False
        words = _words(chunk.text)
        if params.dedupe and any(_jaccard(words, w) >= params.dedupe_jaccard for w in chosen_words):
            stats["duplicates_dropped"] += 1
            stats["duplicate_tokens"] += chunk.evidence_tokens
            return False
        if used + chunk.evidence_tokens > direct_budget:
            return False
        chosen.append(chunk)
        chosen_words.append(words)
        used += chunk.evidence_tokens
        return True

    # Coverage first: the best chunk for each part, if it clears the floor.
    for pool in pools[1:]:
        for chunk in sorted(pool, key=lambda c: -c.score):
            if chunk.score < params.floor:
                break
            if try_add(best[chunk.chunk_id]):
                break
            if any(c.chunk_id == chunk.chunk_id for c in chosen):
                break  # already covered by an earlier part's pick

    top = ranked[0].score if ranked else 0.0
    for chunk in ranked:
        if len(chosen) >= limit:
            stats["stop_reason"] = "max chunks"
            break
        if chunk.score < params.floor:
            stats["stop_reason"] = "floor"
            break
        if (
            params.delta is not None
            and len(chosen) >= params.min_chunks
            and chunk.score < top - params.delta
        ):
            stats["stop_reason"] = "delta"
            break
        if used + chunk.evidence_tokens > direct_budget:
            stats["stop_reason"] = "budget"
            break
        try_add(chunk)
    return chosen, stats


def expand(
    direct: list[RetrievedChunk], params: AdaptiveParams, neighbor_of
) -> list[RetrievedChunk]:
    """Add the chunks before and after strong direct hits, same document and section only,
    within the budget. Returns prompt order: each direct hit's block in document order,
    blocks in the order their direct hits were chosen."""
    used = sum(c.evidence_tokens for c in direct)
    taken = {(c.document_id, c.chunk_index) for c in direct}
    blocks: list[list[RetrievedChunk]] = [[c] for c in direct]
    if params.neighbors:
        for block in blocks:
            hit = block[0]
            if hit.score < params.expand_threshold:
                continue
            for index in (hit.chunk_index - 1, hit.chunk_index + 1):
                if (hit.document_id, index) in taken or index < 0:
                    continue
                neighbor = neighbor_of(hit.document_id, index, hit.score)
                if neighbor is None:
                    continue
                if (
                    hit.section_heading is not None
                    and neighbor.section_heading is not None
                    and neighbor.section_heading != hit.section_heading
                ):
                    continue
                if used + neighbor.evidence_tokens > params.budget:
                    continue
                block.append(neighbor)
                taken.add((hit.document_id, index))
                used += neighbor.evidence_tokens
    return [chunk for block in blocks for chunk in sorted(block, key=lambda c: c.chunk_index)]


def retrieve_adaptive(
    ctx: AppContext, kb: sqlite3.Row, question: str, params: AdaptiveParams
) -> AdaptiveRetrieval:
    check_embedding_lock(ctx, kb)
    plan = analyze(question, split=params.split_parts)
    document_ids = ready_document_ids(ctx, kb)
    if not document_ids:
        return AdaptiveRetrieval(plan, [], [], [], list(plan.parts))

    queries = [question] + (list(plan.parts) if len(plan.parts) > 1 else [])
    pools = [
        load_chunks(ctx, _search(ctx, kb, text, params.pool_size, document_ids)) for text in queries
    ]
    direct, stats = select(plan, pools, params)
    chunks = expand(
        direct,
        params,
        lambda document_id, index, score: load_neighbor(ctx, document_id, index, score),
    )

    part_pools = pools[1:] if len(pools) > 1 else pools
    part_top = [pool[0].score if pool else 0.0 for pool in part_pools]
    uncovered = [
        part for part, score in zip(plan.parts, part_top, strict=True) if score < params.floor
    ]
    merged: dict[str, RetrievedChunk] = {}
    for pool in pools:
        for chunk in pool:
            if chunk.chunk_id not in merged or chunk.score > merged[chunk.chunk_id].score:
                merged[chunk.chunk_id] = chunk
    candidates = sorted(merged.values(), key=lambda c: (-c.score, c.chunk_id))
    return AdaptiveRetrieval(
        plan,
        chunks,
        candidates,
        part_top,
        uncovered,
        stats["duplicates_dropped"],
        stats["duplicate_tokens"],
        stats["stop_reason"],
    )
