"""Question to grounded answer: retrieve, check evidence, generate, validate, trace."""

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

from adaptive_rag.context import AppContext
from adaptive_rag.retrieval import RetrievedChunk, fit_to_budget, retrieve_baseline

from .citations import Citation, build_citation, ids_in_text, strip_unknown_ids
from .prompts import ANSWER_SCHEMA, build_messages, evidence_id

INSUFFICIENT_MESSAGE = "I couldn't find enough evidence in this knowledge base to answer that."


class GenerationFailed(Exception):
    """The LLM's output was cut off or unusable. The message is user-facing."""


class _ModelOutput(BaseModel):
    status: Literal["answered", "partial", "insufficient"]
    answer: str
    cited_ids: list[str]


@dataclass(frozen=True)
class AnswerResult:
    status: Literal["answered", "partial", "insufficient"]
    answer: str
    citations: list[Citation]
    warnings: list[str]
    input_tokens: int | None
    output_tokens: int | None
    timings_ms: dict[str, float]
    trace_id: int


def _resolve(
    output: _ModelOutput, evidence: dict[str, RetrievedChunk]
) -> tuple[str, str, list[Citation], list[str]]:
    """Apply the citation rule: an answer without valid evidence can't count as answered."""
    if output.status == "insufficient":
        return "insufficient", INSUFFICIENT_MESSAGE, [], []

    claimed = list(dict.fromkeys(ids_in_text(output.answer) + output.cited_ids))
    valid = [item for item in claimed if item in evidence]
    if not valid:
        warnings = ["The model's answer had no valid citations, so it was withheld."]
        return "insufficient", INSUFFICIENT_MESSAGE, [], warnings

    status, warnings = output.status, []
    if len(valid) < len(claimed):
        status = "partial"
        warnings.append("Citations to evidence that doesn't exist were removed.")
    citations = [build_citation(item, evidence[item]) for item in valid]
    return status, strip_unknown_ids(output.answer, set(evidence)), citations, warnings


def _write_trace(
    ctx: AppContext,
    kb: sqlite3.Row,
    question: str,
    status: str,
    retrieved: list[RetrievedChunk],
    used: list[RetrievedChunk],
    input_tokens: int | None,
    output_tokens: int | None,
    timings: dict[str, float],
) -> int:
    used_ids = {chunk.chunk_id for chunk in used}
    rows = [
        {
            "chunk_id": chunk.chunk_id,
            "score": round(chunk.score, 4),
            "source": chunk.source,
            "used": chunk.chunk_id in used_ids,
        }
        for chunk in retrieved
    ]
    with ctx.db() as conn:
        return conn.execute(
            "INSERT INTO query_traces (kb_id, question, status, retrieved, input_tokens,"
            " output_tokens, timings_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                kb["id"],
                question,
                status,
                json.dumps(rows),
                input_tokens,
                output_tokens,
                json.dumps(timings),
            ),
        ).lastrowid


def answer_question(ctx: AppContext, kb: sqlite3.Row, question: str) -> AnswerResult:
    settings = ctx.settings
    timings: dict[str, float] = {}

    started = time.perf_counter()
    retrieved = retrieve_baseline(ctx, kb, question, settings.top_k)
    timings["retrieval"] = round((time.perf_counter() - started) * 1000, 1)

    # Gate 1: clearly weak evidence gets no LLM call.
    if not retrieved or retrieved[0].score < settings.score_floor:
        trace_id = _write_trace(
            ctx, kb, question, "insufficient", retrieved, [], None, None, timings
        )
        return AnswerResult(
            "insufficient", INSUFFICIENT_MESSAGE, [], [], None, None, timings, trace_id
        )

    used = fit_to_budget(retrieved, settings.evidence_max_tokens)
    evidence = {evidence_id(position): chunk for position, chunk in enumerate(used)}

    # Gate 2 is the model's own status. Gate 3 is citation validation in _resolve.
    result = ctx.llm.generate(
        build_messages(question, used),
        schema=ANSWER_SCHEMA,
        max_tokens=settings.max_answer_tokens,
    )
    timings["generation"] = round(result.latency_ms, 1)

    try:
        output = _ModelOutput.model_validate_json(result.text)
    except ValidationError as exc:
        _write_trace(
            ctx,
            kb,
            question,
            "failed",
            retrieved,
            used,
            result.input_tokens,
            result.output_tokens,
            timings,
        )
        reason = "was cut off" if result.finish_reason == "length" else "was not usable"
        raise GenerationFailed(f"The model's response {reason}. Please try again.") from exc

    status, answer, citations, warnings = _resolve(output, evidence)
    trace_id = _write_trace(
        ctx,
        kb,
        question,
        status,
        retrieved,
        used,
        result.input_tokens,
        result.output_tokens,
        timings,
    )
    return AnswerResult(
        status,
        answer,
        citations,
        warnings,
        result.input_tokens,
        result.output_tokens,
        timings,
        trace_id,
    )
