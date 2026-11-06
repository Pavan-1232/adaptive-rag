"""Citations are built here from stored metadata, so the model can't invent a location."""

import re
from dataclasses import dataclass

from adaptive_rag.retrieval import RetrievedChunk

_BRACKETED = re.compile(r"\[[^\[\]]*\bE\d+\b[^\[\]]*\]")
_EVIDENCE_ID = re.compile(r"\bE\d+\b")
SNIPPET_CHARS = 240


@dataclass(frozen=True)
class Citation:
    id: str
    document_id: int
    filename: str
    locator_kind: str
    locator_start: int
    locator_end: int
    section_heading: str | None
    label: str
    snippet: str
    score: float
    source: str
    start_char: int = 0
    end_char: int = 0
    passage: str = ""  # the full evidence text, shown when a citation is opened in the UI


def _range(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def format_label(chunk: RetrievedChunk) -> str:
    span = _range(chunk.locator_start, chunk.locator_end)
    section = f', "{chunk.section_heading}"' if chunk.section_heading else ""
    if chunk.locator_kind == "page":
        prefix = "p." if chunk.locator_start == chunk.locator_end else "pp."
        return f"{chunk.filename}, {prefix} {span}"
    if chunk.locator_kind == "paragraph":
        return f"{chunk.filename}{section}, para. {span}"
    noun = "line" if chunk.locator_start == chunk.locator_end else "lines"
    return f"{chunk.filename}{section}, {noun} {span}"


def build_citation(evidence_id: str, chunk: RetrievedChunk) -> Citation:
    return Citation(
        id=evidence_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        locator_kind=chunk.locator_kind,
        locator_start=chunk.locator_start,
        locator_end=chunk.locator_end,
        section_heading=chunk.section_heading,
        label=format_label(chunk),
        snippet=" ".join(chunk.text.split())[:SNIPPET_CHARS],
        score=chunk.score,
        source=chunk.source,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        passage=chunk.text,
    )


def ids_in_text(answer: str) -> list[str]:
    """Evidence IDs in brackets, in order of first appearance. Handles [E1, E2]."""
    found: list[str] = []
    for match in _BRACKETED.finditer(answer):
        found.extend(_EVIDENCE_ID.findall(match.group()))
    return list(dict.fromkeys(found))


def strip_unknown_ids(answer: str, known: set[str]) -> str:
    """Remove citation markers that point at evidence that doesn't exist."""

    def clean(match: re.Match) -> str:
        kept = [item for item in _EVIDENCE_ID.findall(match.group()) if item in known]
        return f"[{', '.join(kept)}]" if kept else ""

    return re.sub(r" +([.,;:])", r"\1", _BRACKETED.sub(clean, answer)).strip()
