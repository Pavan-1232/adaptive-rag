"""One entry point for answering and evaluation: the evidence the model will read.

Baseline: fixed top_k, capped at the hard maximum. Adaptive: retrieve_adaptive within the
evidence target. Both return the scored candidates too, for the gate, traces and metrics.
"""

import sqlite3
from dataclasses import dataclass, field

from adaptive_rag.context import AppContext

from .adaptive import AdaptiveParams, retrieve_adaptive
from .baseline import retrieve_baseline
from .budget import fit_to_budget
from .types import RetrievedChunk


@dataclass
class Evidence:
    mode: str
    candidates: list[RetrievedChunk]  # scored, best first
    used: list[RetrievedChunk]  # what the model reads, in prompt order
    uncovered_parts: list[str] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    @property
    def top_score(self) -> float | None:
        return self.candidates[0].score if self.candidates else None


def retrieve_evidence(ctx: AppContext, kb: sqlite3.Row, question: str) -> Evidence:
    settings = ctx.settings
    if settings.retrieval == "baseline":
        retrieved = retrieve_baseline(ctx, kb, question, settings.top_k)
        used = fit_to_budget(retrieved, settings.evidence_max_tokens)
        return Evidence("baseline", retrieved, used, info={"mode": "baseline"})
    if settings.retrieval != "adaptive":
        raise ValueError(f"unknown retrieval mode: {settings.retrieval}")

    params = AdaptiveParams.from_settings(settings, kb["embedding_model"])
    result = retrieve_adaptive(ctx, kb, question, params)
    info = {
        "mode": "adaptive",
        "kind": result.plan.kind,
        "parts": list(result.plan.parts),
        "part_top_scores": [round(score, 4) for score in result.part_top_scores],
        "uncovered_parts": result.uncovered_parts,
        "stop_reason": result.stop_reason,
        "duplicates_dropped": result.duplicates_dropped,
        "duplicate_tokens": result.duplicate_tokens,
        "evidence_tokens": result.tokens,
        "budget": params.budget,
    }
    return Evidence("adaptive", result.candidates, result.chunks, result.uncovered_parts, info)
