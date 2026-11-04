"""The configuration registry: reuse a winning chunking config on similar documents.

This is configuration caching with rule-based profile matching. It is not machine learning.

| Situation                                                    | Action                     |
|--------------------------------------------------------------|----------------------------|
| Same format, structure, embedding; profile within tolerance  | reuse, no test             |
| Same format, structure, embedding; profile borderline        | cheap re-test vs C1        |
| Cheap re-test: C1 clearly better                             | full optimization          |
| No eligible entry, or a different structure                  | full optimization          |

Tolerances were fixed by reasoning on 2026-11-04, before any regret was measured.
"""

import json
import math
import sqlite3
from dataclasses import dataclass

from .candidates import BY_ID
from .profile import PROFILE_VERSION, Profile

# Strong match: reuse without testing.
STRONG_TABLE_SHARE = 0.02  # absolute difference
STRONG_RATIO = 1.5  # heading density, characters per page, median section tokens
# Borderline: re-test cheaply.
BORDERLINE_TABLE_SHARE = 0.05
BORDERLINE_RATIO = 2.5
RATIO_FIELDS = ("heading_density", "chars_per_page", "median_section_tokens")


@dataclass(frozen=True)
class EmbeddingContext:
    model: str
    digest: str
    prompt_version: str
    extractor_version: str


@dataclass(frozen=True)
class Match:
    action: str  # reuse | retest | optimize
    entry_id: int | None
    candidate_id: str | None
    distance: float | None
    reason: str


def _ratio(a: float | None, b: float | None) -> float:
    """How many times larger one is than the other; 1.0 is identical."""
    a, b = a or 0.0, b or 0.0
    if a <= 0 and b <= 0:
        return 1.0
    if a <= 0 or b <= 0:
        return math.inf
    return max(a, b) / min(a, b)


def compare(profile: Profile, other: dict) -> tuple[str, float]:
    """Return (strong | borderline | different, distance) for two profiles."""
    if (
        profile.format != other["format"]
        or profile.headings_reliable != other["headings_reliable"]
        or profile.has_tables != other["has_tables"]
        or profile.language != other["language"]
    ):
        return "different", math.inf
    table = abs(profile.table_share - other["table_share"])
    ratios = [_ratio(getattr(profile, f), other[f]) for f in RATIO_FIELDS]
    distance = table / BORDERLINE_TABLE_SHARE + sum(
        math.log(r) / math.log(BORDERLINE_RATIO) if math.isfinite(r) else math.inf for r in ratios
    )
    if table <= STRONG_TABLE_SHARE and all(r <= STRONG_RATIO for r in ratios):
        return "strong", distance
    if table <= BORDERLINE_TABLE_SHARE and all(r <= BORDERLINE_RATIO for r in ratios):
        return "borderline", distance
    return "different", distance


def eligible_entries(conn: sqlite3.Connection, context: EmbeddingContext) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM chunking_registry WHERE stale = 0 AND embedding_model = ?"
        " AND embedding_digest = ? AND embedding_prompt_version = ? AND extractor_version = ?"
        " AND profile_version = ?",
        (
            context.model,
            context.digest,
            context.prompt_version,
            context.extractor_version,
            PROFILE_VERSION,
        ),
    ).fetchall()
    # An entry made with older chunker code no longer describes what that candidate produces.
    return [r for r in rows if BY_ID[r["candidate_id"]].version == r["chunker_version"]]


def find_match(profile: Profile, entries: list) -> Match:
    best: tuple[str, float, object] | None = None
    for entry in entries:
        kind, distance = compare(profile, json.loads(entry["profile"]))
        if kind != "different" and (best is None or distance < best[1]):
            best = (kind, distance, entry)
    if best is None:
        return Match("optimize", None, None, None, "no similar document in the registry")
    kind, distance, entry = best
    action = "reuse" if kind == "strong" else "retest"
    return Match(
        action,
        entry["id"],
        entry["candidate_id"],
        round(distance, 3),
        f"{kind} match with {entry['source_document']}",
    )


def record_winner(
    conn: sqlite3.Connection, result, context: EmbeddingContext, profile: Profile
) -> int:
    candidate = BY_ID[result.winner]
    winner = next(c for c in result.candidates if c.id == result.winner)
    return conn.execute(
        "INSERT INTO chunking_registry (candidate_id, strategy, size_tokens, overlap_tokens,"
        " chunker_version, embedding_model, embedding_digest, embedding_prompt_version,"
        " extractor_version, profile_version, profile, selection_recall, confirmation_recall,"
        " question_count, runtime_s, source_document)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            candidate.id,
            candidate.strategy,
            candidate.size,
            candidate.overlap,
            candidate.version,
            context.model,
            context.digest,
            context.prompt_version,
            context.extractor_version,
            profile.version,
            json.dumps(profile.to_dict()),
            winner.selection_recall,
            winner.confirmation_recall,
            result.questions_selection + result.questions_confirmation,
            result.timings_s.get("total", 0.0),
            result.document,
        ),
    ).lastrowid


def mark_reused(conn: sqlite3.Connection, entry_id: int, retest: dict | None = None) -> None:
    conn.execute(
        "UPDATE chunking_registry SET times_reused = times_reused + 1,"
        " last_retest = COALESCE(?, last_retest) WHERE id = ?",
        (json.dumps(retest) if retest else None, entry_id),
    )


def mark_stale(conn: sqlite3.Connection, context: EmbeddingContext) -> int:
    """Entries for another embedding model, prompt, extractor, or chunker version go stale."""
    count = 0
    for row in conn.execute("SELECT * FROM chunking_registry WHERE stale = 0").fetchall():
        current = (
            row["embedding_model"] == context.model
            and row["embedding_digest"] == context.digest
            and row["embedding_prompt_version"] == context.prompt_version
            and row["extractor_version"] == context.extractor_version
            and BY_ID[row["candidate_id"]].version == row["chunker_version"]
        )
        if not current:
            conn.execute("UPDATE chunking_registry SET stale = 1 WHERE id = ?", (row["id"],))
            count += 1
    return count
