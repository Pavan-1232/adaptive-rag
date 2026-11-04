"""Full optimization for one document: profile, sample, generate questions, score candidates,
select by the rule. Every cap is enforced here and recorded in the result.

Order matters for memory on 16 GB: all LLM work (question generation) happens first, then the
LLM is unloaded, then only the embedding model runs.
"""

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from adaptive_rag.chunking import MAX_CHUNK_TOKENS, Chunk, count_tokens
from adaptive_rag.evaluation.benchmark import BenchmarkQuestion
from adaptive_rag.evaluation.questions import generate_for_plan
from adaptive_rag.loaders import ExtractedDocument
from adaptive_rag.providers import EmbeddingInputTooLong

from .candidates import CANDIDATES, Candidate, build_chunks
from .profile import Profile, profile_document
from .sampling import question_plan, sample_regions
from .scoring import DocumentChunks, InMemoryIndex, question_spans, score_question
from .selection import select

OPTIMIZER_VERSION = "optimizer-1"


@dataclass(frozen=True)
class Caps:
    """Starting values from DESIGN.md section 5; Stage 4 measures them."""

    max_questions: int = 40
    confirmation_questions: int = 10
    max_llm_calls: int = 60  # planned windows, including ones whose question is rejected
    max_candidates: int = 7
    time_budget_s: float = 720.0  # 12 minutes per document
    generation_share: float = 0.7  # question generation stops at 70% of the time budget
    min_selection_questions: int = 10  # fewer, and the control C1 is kept


@dataclass
class CandidateResult:
    id: str
    status: str  # scored | not applicable | skipped: <reason> | failed: <reason>
    chunks_in_sample: int = 0
    storage_tokens: int = 0
    seconds: float = 0.0
    selection_recall: float | None = None
    difference_vs_leader: tuple[float, float, float] | None = None
    tied_with_leader: bool | None = None
    confirmation_recall: float | None = None


@dataclass
class OptimizationResult:
    document: str
    optimizer_version: str
    profile: dict
    caps: dict
    sample_tokens: int
    regions: list[tuple[int, int]]
    questions_selection: int
    questions_confirmation: int
    question_types: dict[str, int]
    rejected: dict[str, int]
    llm_calls: int
    candidates: list[CandidateResult]
    winner: str
    winner_reason: str
    timings_s: dict[str, float] = field(default_factory=dict)
    stopped_early: list[str] = field(default_factory=list)
    per_question: dict[str, list[dict]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _in_sample(chunks: list[Chunk], regions: list[tuple[int, int]]) -> list[Chunk]:
    """Chunks touching any sampled region. Every candidate is charged the same way."""
    return [c for c in chunks if any(c.start < e and c.end > s for s, e in regions)]


def _split(questions: list[BenchmarkQuestion], confirmation: int) -> tuple[list, list]:
    """Every k-th question goes to confirmation, so both sets spread across the document."""
    if len(questions) <= confirmation:
        return questions, []
    step = len(questions) / confirmation
    picks = {int(i * step + step - 1) for i in range(confirmation)}
    return (
        [q for i, q in enumerate(questions) if i not in picks],
        [q for i, q in enumerate(questions) if i in picks],
    )


def optimize_document(
    doc: ExtractedDocument,
    name: str,
    fmt: str,
    embedder,
    llm,
    caps: Caps | None = None,
    candidates: tuple[Candidate, ...] = CANDIDATES,
    clock: Callable[[], float] = time.monotonic,
    profile: Profile | None = None,
) -> OptimizationResult:
    caps = caps or Caps()
    started = clock()
    deadline = started + caps.time_budget_s
    timings: dict[str, float] = {}
    stopped: list[str] = []
    title = name.rsplit(".", 1)[0]

    profile = profile or profile_document(doc, fmt)
    regions = sample_regions(doc)
    sample_tokens = sum(count_tokens(doc.text[s:e]) for s, e in regions)

    plan = question_plan(doc, regions, min(caps.max_llm_calls, caps.max_questions))
    # Extra windows, offset by half a window, replace questions the filters reject.
    extra = (
        question_plan(doc, regions, caps.max_llm_calls - len(plan))
        if caps.max_llm_calls > len(plan)
        else []
    )
    extra = [(min(s + (e - s) // 2, e - 1), e, kind) for s, e, kind in extra]
    generation_deadline = started + caps.time_budget_s * caps.generation_share
    t = clock()
    questions, rejected, calls = generate_for_plan(
        llm, doc, name, plan + extra, caps.max_questions, generation_deadline, clock
    )
    timings["questions"] = clock() - t
    if rejected.get("time cap"):
        stopped.append("question generation hit the time cap")
    llm.unload()  # one model at a time on 16 GB

    selection_qs, confirmation_qs = _split(questions, caps.confirmation_questions)
    spans = {q.id: question_spans(q, doc) for q in questions}
    t = clock()
    query_vectors = {q.id: embedder.embed_query(q.question) for q in questions}
    timings["query_embeddings"] = clock() - t

    results: list[CandidateResult] = []
    selection_scores: dict[str, list[float]] = {}
    confirmation_scores: dict[str, list[float]] = {}
    per_question: dict[str, list[dict]] = {}
    storage: dict[str, int] = {}
    tried = 0
    # Semantic last: it is the costliest and the first to go when time runs out.
    for candidate in sorted(candidates, key=lambda c: c.strategy == "semantic"):
        if not candidate.applies(profile):
            results.append(CandidateResult(candidate.id, "not applicable"))
            continue
        if tried >= caps.max_candidates:
            results.append(CandidateResult(candidate.id, "skipped: candidate cap"))
            continue
        if clock() >= deadline:
            results.append(CandidateResult(candidate.id, "skipped: time cap"))
            stopped.append(f"{candidate.id} skipped by the time cap")
            continue
        tried += 1
        t = clock()
        try:
            chunks = build_chunks(candidate, doc, embedder, title, regions)
            sampled = _in_sample(chunks, regions)
            if any(c.evidence_tokens > MAX_CHUNK_TOKENS for c in sampled):
                raise EmbeddingInputTooLong("a chunk exceeds the embedding limit")
            index = InMemoryIndex([DocumentChunks(name, doc, sampled, title)], embedder)
        except EmbeddingInputTooLong as exc:
            results.append(CandidateResult(candidate.id, f"failed: {exc}"))
            continue
        scores = {
            q.id: score_question(index, query_vectors[q.id], q.id, spans[q.id]) for q in questions
        }
        selection_scores[candidate.id] = [scores[q.id].recall_at_budget for q in selection_qs]
        confirmation_scores[candidate.id] = [scores[q.id].recall_at_budget for q in confirmation_qs]
        per_question[candidate.id] = [asdict(scores[q.id]) for q in questions]
        storage[candidate.id] = index.storage_tokens
        results.append(
            CandidateResult(
                candidate.id,
                "scored",
                chunks_in_sample=len(sampled),
                storage_tokens=index.storage_tokens,
                seconds=round(clock() - t, 2),
            )
        )
    timings["candidates"] = sum(r.seconds for r in results)

    if len(selection_qs) < caps.min_selection_questions or "C1" not in selection_scores:
        winner = "C1"
        reason = f"only {len(selection_qs)} selection questions; kept the control"
        rankings = []
    else:
        winner, rankings = select(selection_scores, storage)
        tied = [r.candidate_id for r in rankings if r.tied_with_leader]
        reason = (
            f"leader {rankings[0].candidate_id}; tied with leader: {', '.join(tied)};"
            " simplest tied wins"
        )
    by_id = {r.candidate_id: r for r in rankings}
    for result in results:
        if result.id in by_id:
            ranking = by_id[result.id]
            result.selection_recall = round(ranking.mean, 4)
            result.difference_vs_leader = tuple(round(x, 4) for x in ranking.difference_vs_leader)
            result.tied_with_leader = ranking.tied_with_leader
        if confirmation_scores.get(result.id):
            values = confirmation_scores[result.id]
            result.confirmation_recall = round(sum(values) / len(values), 4)

    timings["total"] = clock() - started
    types: dict[str, int] = {}
    for question in questions:
        types[question.type] = types.get(question.type, 0) + 1
    return OptimizationResult(
        document=name,
        optimizer_version=OPTIMIZER_VERSION,
        profile=profile.to_dict(),
        caps=asdict(caps),
        sample_tokens=sample_tokens,
        regions=regions,
        questions_selection=len(selection_qs),
        questions_confirmation=len(confirmation_qs),
        question_types=types,
        rejected=rejected,
        llm_calls=calls,
        candidates=results,
        winner=winner,
        winner_reason=reason,
        timings_s={k: round(v, 2) for k, v in timings.items()},
        stopped_early=stopped,
        per_question=per_question,
    )
