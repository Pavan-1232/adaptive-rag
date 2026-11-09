"""Question to grounded answer: retrieve, check evidence, generate, validate, trace."""

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ValidationError

from adaptive_rag.context import AppContext
from adaptive_rag.mcq import (
    KEY_MISMATCH_MESSAGE,
    KEY_MISMATCH_WARNING,
    NOT_GIVEN_MESSAGE,
    NOT_GIVEN_WARNING,
    contradicts_key,
    picks_unkeyed_option,
)
from adaptive_rag.providers.cloud import cloud_llm
from adaptive_rag.retrieval import Evidence, RetrievedChunk, retrieve_evidence

from .citations import Citation, build_citation, ids_in_text, strip_unknown_ids
from .prompts import ANSWER_SCHEMA, build_messages, evidence_id, has_table

INSUFFICIENT_MESSAGE = "I couldn't find enough evidence in this knowledge base to answer that."


class GenerationFailed(Exception):
    """The LLM's output was cut off or unusable. The message is user-facing."""


class CloudNotAllowed(Exception):
    """A cloud model was requested for a knowledge base that hasn't opted in. User-facing."""


def _choose_llm(ctx: AppContext, kb: sqlite3.Row, provider: str):
    """Ollama, or a cloud adapter. Checked before retrieval, so a refusal makes no call at all."""
    if provider == "ollama":
        return ctx.llm
    if not kb["allow_cloud"]:
        raise CloudNotAllowed(
            f"Knowledge base '{kb['name']}' doesn't allow cloud models, because they send document"
            " text off this machine. Turn on allow_cloud for it first."
        )
    return cloud_llm(ctx.settings, provider, ctx.cloud_transport)


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
    evidence: Evidence,
    used: list[RetrievedChunk],
    input_tokens: int | None,
    output_tokens: int | None,
    timings: dict[str, float],
) -> int:
    pieces = [piece for chunk in used for piece in chunk.pieces]  # merged blocks unpacked
    used_ids = {piece.chunk_id for piece in pieces}
    candidate_ids = {chunk.chunk_id for chunk in evidence.candidates}
    # Expansions aren't in the scored pool, so they are added to the trace explicitly.
    listed = evidence.candidates + [p for p in pieces if p.chunk_id not in candidate_ids]
    rows = [
        {
            "chunk_id": chunk.chunk_id,
            "score": round(chunk.score, 4),
            "source": next((p.source for p in pieces if p.chunk_id == chunk.chunk_id), "direct"),
            "used": chunk.chunk_id in used_ids,
        }
        for chunk in listed
    ]
    with ctx.db() as conn:
        return conn.execute(
            "INSERT INTO query_traces (kb_id, question, status, retrieved, input_tokens,"
            " output_tokens, timings_ms, retrieval) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                kb["id"],
                question,
                status,
                json.dumps(rows),
                input_tokens,
                output_tokens,
                json.dumps(timings),
                json.dumps(evidence.info),
            ),
        ).lastrowid


def answer_question(
    ctx: AppContext, kb: sqlite3.Row, question: str, provider: str = "ollama"
) -> AnswerResult:
    settings = ctx.settings
    timings: dict[str, float] = {}
    llm = _choose_llm(ctx, kb, provider)

    started = time.perf_counter()
    retrieved = retrieve_evidence(ctx, kb, question)
    timings["retrieval"] = round((time.perf_counter() - started) * 1000, 1)

    # Gate 1: clearly weak evidence gets no LLM call.
    top = retrieved.top_score
    if top is None or not retrieved.used or top < settings.floor_for(kb["embedding_model"]):
        trace_id = _write_trace(
            ctx, kb, question, "insufficient", retrieved, [], None, None, timings
        )
        return AnswerResult(
            "insufficient", INSUFFICIENT_MESSAGE, [], [], None, None, timings, trace_id
        )

    used = retrieved.used
    evidence = {evidence_id(position): chunk for position, chunk in enumerate(used)}
    uncovered = retrieved.uncovered_parts if settings.adaptive_part_notice else []
    table_rule = settings.table_prompt and has_table(used)
    retrieved.info["table_prompt_applied"] = table_rule
    retrieved.info["llm"] = {"provider": provider, "model": llm.model}  # never the key

    # Gate 2 is the model's own status. Gate 3 is citation validation in _resolve.
    result = llm.generate(
        build_messages(question, used, uncovered, table_rule),
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
    # Gate 4: an MCQ option the evidence never confirms is withheld (prompt rule wasn't enough),
    # and so is one that differs from the answer key linked by retrieval.
    texts = [c.evidence_text for c in used]
    keyed = {link["keyed"] for link in retrieved.info.get("answer_keys", []) if link["keyed"]}
    if status != "insufficient" and keyed and contradicts_key(answer, texts, keyed):
        status, answer = "partial", KEY_MISMATCH_MESSAGE
        warnings = [*warnings, KEY_MISMATCH_WARNING]
    elif status != "insufficient" and picks_unkeyed_option(answer, texts):
        status, answer = "partial", NOT_GIVEN_MESSAGE
        warnings = [*warnings, NOT_GIVEN_WARNING]
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
