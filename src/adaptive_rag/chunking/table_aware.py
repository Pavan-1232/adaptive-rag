"""C7: recursive chunking that keeps tables apart from prose and splits them only between rows.

A table that fits becomes one chunk, title and header included. A larger table is cut at line
boundaries; every piece after the first carries the header as a second character range, so its
rows are never embedded or read without their column labels. Prose around tables is split by
the recursive chunker. Tables get no overlap: the header gives continuation pieces their context.
"""

from adaptive_rag.loaders import ExtractedDocument

from .base import Chunk, count_tokens, make_chunk
from .recursive import check_settings, split_ranges
from .tables import VERSION as TABLES_VERSION
from .tables import Table, find_tables, header_context

STRATEGY = "table_aware"
VERSION = f"table-aware-1+{TABLES_VERSION}"

Piece = tuple[int, int, tuple[int, int] | None]


def _line_ends(text: str, start: int, end: int) -> list[int]:
    """Positions just after each line in [start, end), the only places a table may be cut."""
    ends, position = [], start
    while position < end:
        newline = text.find("\n", position, end)
        position = end if newline < 0 else newline + 1
        ends.append(position)
    return ends


def _table_ranges(text: str, table: Table, size: int) -> list[Piece]:
    if count_tokens(text[table.start : table.end]) <= size:
        return [(table.start, table.end, None)]
    context = header_context(text, table)
    context_tokens = count_tokens(text[slice(*context)]) + 1 if context else 0
    if size - context_tokens < size // 2:
        context, context_tokens = None, 0  # a header this large would crowd out the rows
    pieces: list[Piece] = []

    def limit() -> int:
        # Continuation pieces leave room for the header they carry.
        return size - context_tokens if pieces else size

    def emit(start: int, end: int) -> None:
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            pieces.append((start, end, context if pieces else None))

    start, fits = table.start, None  # fits: the furthest line end that still fits
    for cut in _line_ends(text, table.start, table.end):
        if count_tokens(text[start:cut]) <= limit():
            fits = cut
            continue
        if fits is not None:
            emit(start, fits)
            start, fits = fits, None
            if count_tokens(text[start:cut]) <= limit():
                fits = cut
                continue
        # One line is too long by itself: split inside it, as prose.
        for left, right in split_ranges(text, start, cut, limit(), 0):
            emit(left, right)
        start, fits = cut, None
    if start < table.end:
        emit(start, table.end)
    return pieces


def chunk_table_aware(doc: ExtractedDocument, size: int = 512, overlap: int = 50) -> list[Chunk]:
    check_settings(size, overlap)
    text = doc.text
    chunks: list[Chunk] = []

    def add(start: int, end: int, context=None, is_table=False) -> None:
        chunks.append(make_chunk(doc, len(chunks), start, end, context, is_table))

    position = 0
    for table in find_tables(text):
        for start, end in split_ranges(text, position, table.start, size, overlap):
            add(start, end)
        for start, end, context in _table_ranges(text, table, size):
            add(start, end, context, is_table=True)
        position = table.end
    for start, end in split_ranges(text, position, len(text), size, overlap):
        add(start, end)
    return chunks
