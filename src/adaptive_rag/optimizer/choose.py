"""Choose a chunking config for a document at ingest: fixed, forced, or adaptive.

Adaptive: profile the document, look it up in the registry, then reuse, re-test cheaply, or run
the full optimization (DESIGN.md section 5). Every decision is returned with its reason.
"""

import json
import time
from dataclasses import dataclass, field

from adaptive_rag.loaders import ExtractedDocument

from .candidates import BY_ID
from .optimize import optimize_document, retest_config
from .profile import profile_document
from .registry import (
    EmbeddingContext,
    eligible_entries,
    find_match,
    mark_reused,
    mark_stale,
    record_winner,
)


@dataclass
class Choice:
    candidate_id: str | None  # None means the legacy fixed chunker from settings
    action: str  # fixed | forced | reuse | retest-kept | optimize
    registry_id: int | None = None
    seconds: float = 0.0
    detail: dict = field(default_factory=dict)

    def detail_json(self) -> str:
        return json.dumps(self.detail)


def choose_chunking(ctx, doc: ExtractedDocument, filename: str, fmt: str, extractor: str) -> Choice:
    started = time.monotonic()
    mode = ctx.settings.chunking
    if mode == "fixed":
        return Choice(None, "fixed")
    if mode in BY_ID:
        return Choice(mode, "forced")
    if mode != "adaptive":
        raise ValueError(f"unknown chunking mode: {mode}")

    profile = profile_document(doc, fmt)
    embedder = ctx.embedder
    context = EmbeddingContext(
        embedder.model, embedder.version(), embedder.prompt_version, extractor
    )
    with ctx.db() as conn:
        stale = mark_stale(conn, context)
        match = find_match(profile, eligible_entries(conn, context))
    detail = {"profile": profile.to_dict(), "match": vars(match), "marked_stale": stale}

    if match.action == "reuse":
        with ctx.db() as conn:
            mark_reused(conn, match.entry_id)
        return Choice(
            match.candidate_id, "reuse", match.entry_id, time.monotonic() - started, detail
        )

    if match.action == "retest":
        if match.candidate_id == "C1":
            detail["retest"] = "skipped: the cached config is the control"
            with ctx.db() as conn:
                mark_reused(conn, match.entry_id)
            return Choice("C1", "retest-kept", match.entry_id, time.monotonic() - started, detail)
        keep, result = retest_config(
            doc, filename, fmt, embedder, ctx.llm, match.candidate_id, profile=profile
        )
        summary = {
            "kept": keep,
            "candidates": [vars(c) for c in result.candidates],
            "questions": result.questions_selection,
            "seconds": result.timings_s.get("total"),
        }
        detail["retest"] = summary
        if keep:
            with ctx.db() as conn:
                mark_reused(conn, match.entry_id, summary)
            return Choice(
                match.candidate_id,
                "retest-kept",
                match.entry_id,
                time.monotonic() - started,
                detail,
            )

    result = optimize_document(doc, filename, fmt, embedder, ctx.llm, profile=profile)
    with ctx.db() as conn:
        entry_id = record_winner(conn, result, context, profile)
    detail["optimization"] = result.to_dict()
    return Choice(result.winner, "optimize", entry_id, time.monotonic() - started, detail)
