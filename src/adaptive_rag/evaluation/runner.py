"""Run a benchmark against one system configuration and record per-question results."""

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from adaptive_rag.answering import GenerationFailed, answer_question
from adaptive_rag.config import Settings
from adaptive_rag.context import AppContext
from adaptive_rag.db import migrate
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.providers import EmbeddingProvider, LLMProvider
from adaptive_rag.retrieval import Evidence, RetrievedChunk, retrieve_baseline, retrieve_evidence
from adaptive_rag.vectorstore import VectorStore

from .benchmark import BenchmarkQuestion, ManifestDocument
from .judge import compare_to_reference, judge_answer
from .metrics import (
    RankedChunk,
    Span,
    evidence_recall,
    hit_at_k,
    part_coverage,
    recall_at_budget,
    recall_at_k,
    reciprocal_rank,
)
from .spans import locate_quote, overlap, page_range

POOL_SIZE = 30
# Matches five 512-token chunks. At 2000, only three fit and a 1024-token chunk fits once.
RECALL_BUDGET_TOKENS = 2560
METRIC_K = 5


@dataclass
class QuestionResult:
    id: str
    document: str
    type: str
    question: str
    answerable: bool
    source: str
    top_score: float | None
    recall_at_budget: float | None = None
    recall_at_5: float | None = None
    hit_at_5: float | None = None
    reciprocal_rank: float | None = None
    # Required facts (evidence items), and the share of them hit within the budget.
    parts: int | None = None
    part_coverage: float | None = None
    all_parts_covered: float | None = None
    # Stage 5: measured on the evidence actually sent to the model, whatever the system.
    recall_sent: float | None = None
    part_coverage_sent: float | None = None
    tokens_sent: int | None = None
    retrieval_info: dict = field(default_factory=dict)
    status: str | None = None
    answer: str | None = None
    citations: list[str] = field(default_factory=list)
    citation_on_evidence: bool | None = None
    citation_precision: float | None = None
    faithfulness: float | None = None
    addresses_question: bool | None = None
    reference_verdict: str | None = None
    judged: bool = False
    judge_claims: list[dict] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)
    error: str | None = None


def build_index(
    settings: Settings,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    documents: list[ManifestDocument],
    documents_root: Path,
    kb_name: str,
) -> tuple[AppContext, object, dict[str, dict]]:
    """Index documents into a knowledge base, reusing it if already built."""
    ctx = AppContext(settings, embedder, llm, VectorStore(settings.chroma_dir))
    with ctx.db() as conn:
        migrate(conn)
        kb = conn.execute("SELECT * FROM knowledge_bases WHERE name = ?", (kb_name,)).fetchone()
    if kb is None:
        kb = create_knowledge_base(ctx, kb_name)

    indexed: dict[str, dict] = {}
    for item in documents:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / item.name
            shutil.copyfile(documents_root / item.file, temp_path)
            document, job_id, _ = register_upload(ctx, kb, temp_path, item.name)
        if job_id is not None:
            run_ingest_job(ctx, job_id)
        with ctx.db() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document["id"],)).fetchone()
        if row["status"] != "ready":
            raise RuntimeError(f"{item.name} failed to index: {row['error']}")
        indexed[item.name] = dict(row)
    return ctx, kb, indexed


def evidence_spans(question: BenchmarkQuestion, indexed: dict[str, dict]) -> list[Span]:
    spans: list[Span] = []
    text = indexed[question.document]["canonical_text"]
    units = indexed[question.document]["units"]
    units = json.loads(units) if isinstance(units, str) else units
    for item in question.evidence:
        found = [
            locate_quote(text, option.quote, page_range(units, option.page))
            for option in (item, *item.alternatives)
        ]
        if None in found:
            raise ValueError(f"{question.id}: evidence quote not found in {question.document}")
        alternatives = tuple(Span(question.document, *where) for where in found[1:])
        spans.append(Span(question.document, *found[0], alternatives))
    return spans


def _ranked(chunks: list[RetrievedChunk]) -> list[RankedChunk]:
    return [
        RankedChunk(chunk.filename, chunk.start_char, chunk.end_char, chunk.evidence_tokens)
        for chunk in chunks
    ]


def _touches_evidence(filename: str, start: int, end: int, spans: list[Span]) -> bool:
    return any(
        option.document == filename and overlap(start, end, option.start, option.end) > 0
        for span in spans
        for option in span.options()
    )


def evaluate_retrieval(
    ctx: AppContext, kb, question: BenchmarkQuestion, spans: list[Span]
) -> tuple[QuestionResult, Evidence]:
    """Rank metrics use the full question's top-30 pool, as in Stages 3-4, so they stay
    comparable. The *_sent metrics use the evidence the configured system actually sends."""
    pool = retrieve_baseline(ctx, kb, question.question, POOL_SIZE)
    evidence = retrieve_evidence(ctx, kb, question.question)
    result = QuestionResult(
        id=question.id,
        document=question.document,
        type=question.type,
        question=question.question,
        answerable=question.answerable,
        source=question.source,
        top_score=pool[0].score if pool else None,
    )
    if question.answerable:
        ranked = _ranked(pool)
        result.recall_at_budget = recall_at_budget(ranked, spans, RECALL_BUDGET_TOKENS)
        result.recall_at_5 = recall_at_k(ranked, spans, METRIC_K)
        result.hit_at_5 = hit_at_k(ranked, spans, METRIC_K)
        result.reciprocal_rank = reciprocal_rank(ranked, spans)
        result.parts = len(spans)
        result.part_coverage = part_coverage(ranked, spans, RECALL_BUDGET_TOKENS)
        result.all_parts_covered = float(result.part_coverage == 1.0)
        sent = _ranked(evidence.used)
        result.recall_sent = evidence_recall(sent, spans)
        result.part_coverage_sent = part_coverage(sent, spans, 10**9)
    result.tokens_sent = sum(chunk.evidence_tokens for chunk in evidence.used)
    result.retrieval_info = evidence.info
    return result, evidence


def evaluate_answer(
    ctx: AppContext,
    kb,
    question: BenchmarkQuestion,
    spans: list[Span],
    result: QuestionResult,
    evidence: Evidence,
) -> None:
    """Generate with the score gate off, so calibration can replay any floor afterwards."""
    try:
        answer = answer_question(ctx, kb, question.question)
    except GenerationFailed as exc:
        result.error = str(exc)
        return
    result.status = answer.status
    result.answer = answer.answer
    result.citations = [citation.label for citation in answer.citations]
    result.input_tokens = answer.input_tokens
    result.output_tokens = answer.output_tokens
    result.timings_ms = answer.timings_ms
    if question.answerable and answer.citations:
        on_evidence = [
            _touches_evidence(citation.filename, citation.start_char, citation.end_char, spans)
            for citation in answer.citations
        ]
        result.citation_on_evidence = any(on_evidence)
        result.citation_precision = sum(on_evidence) / len(on_evidence)


def evaluate_judgment(
    judge: LLMProvider,
    settings: Settings,
    question: BenchmarkQuestion,
    result: QuestionResult,
    evidence: Evidence,
) -> None:
    if result.status not in ("answered", "partial") or not result.answer:
        return
    if question.answerable:
        reference = question.expected_answer or " ".join(e.quote for e in question.evidence)
        result.reference_verdict = compare_to_reference(
            judge, question.question, result.answer, reference
        )
    used = evidence.used  # the same evidence the answer saw, for baseline and adaptive
    judgment = judge_answer(judge, question.question, result.answer, [chunk.text for chunk in used])
    if judgment is None:
        return
    result.faithfulness = judgment.faithfulness
    result.addresses_question = judgment.addresses_question
    result.judge_claims = [claim.model_dump() for claim in judgment.claims]


def run_benchmark(
    ctx: AppContext,
    kb,
    indexed: dict[str, dict],
    questions: list[BenchmarkQuestion],
    answers: bool = True,
    judge: LLMProvider | None = None,
    on_progress=None,
    done: dict[str, QuestionResult] | None = None,
    on_save=None,
) -> list[QuestionResult]:
    """Retrieval and answers first, then judging, so the two LLMs never need to share memory.

    Questions in done are not answered again, and judged ones are not judged again, so a stopped
    run can resume. on_save receives all results so far after every question and judge call.
    """
    done = done or {}
    results: list[tuple[BenchmarkQuestion, QuestionResult, Evidence | None]] = []

    def save() -> None:
        if on_save:
            on_save([result for _, result, _ in results])

    original_floor, original_floors = ctx.settings.score_floor, ctx.settings.score_floors
    ctx.settings.score_floor, ctx.settings.score_floors = -1.0, {}
    try:
        for question in questions:
            if question.id in done:
                results.append((question, done[question.id], None))
                continue
            spans = evidence_spans(question, indexed) if question.answerable else []
            result, evidence = evaluate_retrieval(ctx, kb, question, spans)
            if answers:
                evaluate_answer(ctx, kb, question, spans, result, evidence)
            results.append((question, result, evidence))
            save()
            if on_progress:
                on_progress(result)
    finally:
        ctx.settings.score_floor, ctx.settings.score_floors = original_floor, original_floors

    pending = [item for item in results if not item[1].judged]
    if judge is not None and answers and pending:
        ctx.llm.unload()
        for question, result, evidence in pending:
            if evidence is None:
                # Resumed: rebuild the evidence the answer saw. Retrieval is deterministic.
                evidence = retrieve_evidence(ctx, kb, question.question)
            evaluate_judgment(judge, ctx.settings, question, result, evidence)
            result.judged = True
            save()
            if on_progress:
                on_progress(result)
        judge.unload()
    return [result for _, result, _ in results]


def save_results(
    path: Path, metadata: dict, results: list[QuestionResult], complete: bool = True
) -> None:
    """Write via a temporary file, so a stop mid-write never leaves a broken results file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {**metadata, "complete": complete},
        "results": [asdict(result) for result in results],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    os.replace(temporary, path)


# A run can only resume if these match, or its results would mix two setups.
RESUME_KEYS = (
    "system",
    "chunking",
    "set",
    "embedding_model",
    "embedding_version",
    "llm_model",
    "judge_model",
    "judge_prompt",
    "judge_check",
    "recall_budget_tokens",
    "questions_sha256",
    "retrieval_only",
    "retrieval",
    "table_prompt",
    "adaptive_params",
)


def load_partial(path: Path) -> tuple[dict, dict[str, QuestionResult]]:
    payload = json.loads(path.read_text())
    results = {row["id"]: QuestionResult(**row) for row in payload["results"]}
    return payload["metadata"], results


def resume_conflicts(saved: dict, current: dict) -> list[str]:
    return [key for key in RESUME_KEYS if saved.get(key) != current.get(key)]


def is_complete(payload: dict) -> bool:
    """Files written before resumable runs have no flag, and were only written when complete."""
    return payload["metadata"].get("complete", True)
