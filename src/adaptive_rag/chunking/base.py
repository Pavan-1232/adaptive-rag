"""Shared chunking types. Every chunk is a character range in the canonical text."""

from bisect import bisect_right
from dataclasses import dataclass

import tiktoken

from adaptive_rag.loaders import ExtractedDocument

# EmbeddingGemma has a 2K context. Chunks stay well under it, per the design.
MAX_CHUNK_TOKENS = 1024

_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """A provider-neutral estimate. Actual usage is logged from provider counts."""
    return len(_encoding.encode_ordinary(text))


@dataclass(frozen=True)
class Chunk:
    index: int
    start: int
    end: int
    text: str
    token_count: int
    locator_start: int
    locator_end: int
    section_heading: str | None


def locate(doc: ExtractedDocument, start: int, end: int) -> tuple[int, int]:
    """Return the first and last unit numbers that a character range touches."""
    starts = [unit.start for unit in doc.units]
    first = max(bisect_right(starts, start) - 1, 0)
    last = max(bisect_right(starts, max(end - 1, start)) - 1, first)
    # A range that begins in a gap between units belongs to the next unit.
    if doc.units[first].end <= start and first < last:
        first += 1
    return doc.units[first].number, doc.units[last].number


def section_at(doc: ExtractedDocument, position: int) -> str | None:
    """Return the heading of the section containing a character position."""
    for section in reversed(doc.sections):
        if section.start <= position:
            return section.heading
    return None
