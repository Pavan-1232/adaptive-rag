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
    # C7 only: a second character range holding a table's title and column header, added to
    # the embedding input and shown to the LLM as context. The chunk's own range stays exact.
    context_start: int | None = None
    context_end: int | None = None
    is_table: bool = False
    # Tokens of the context plus its separator. Budgets charge evidence_tokens, never just
    # token_count, so C7's header is not free.
    context_tokens: int = 0

    @property
    def evidence_tokens(self) -> int:
        return self.token_count + self.context_tokens


def make_chunk(
    doc: ExtractedDocument,
    index: int,
    start: int,
    end: int,
    context: tuple[int, int] | None = None,
    is_table: bool = False,
) -> Chunk:
    """Build a chunk for a character range, filling in its tokens, locators, and section."""
    text = doc.text[start:end]
    locator_start, locator_end = locate(doc, start, end)
    return Chunk(
        index=index,
        start=start,
        end=end,
        text=text,
        token_count=count_tokens(text),
        locator_start=locator_start,
        locator_end=locator_end,
        section_heading=section_at(doc, start),
        context_start=context[0] if context else None,
        context_end=context[1] if context else None,
        is_table=is_table,
        context_tokens=count_tokens(doc.text[context[0] : context[1]] + "\n") if context else 0,
    )


def context_text(doc_text: str, chunk: Chunk) -> str | None:
    if chunk.context_start is None or chunk.context_end is None:
        return None
    return doc_text[chunk.context_start : chunk.context_end]


def embedding_text(doc_text: str, chunk: Chunk) -> str:
    """The chunk text, preceded by its table context when it has one. The LLM sees the same."""
    context = context_text(doc_text, chunk)
    return chunk.text if context is None else context + "\n" + chunk.text


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
