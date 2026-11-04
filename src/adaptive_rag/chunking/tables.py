"""Find tables in canonical text with line rules, no LLM.

PDF extraction flattens a table into lines like "Research and development $ 4,540 $ 3,969".
A table is a run of such rows, with at most a couple of label lines between them ("Assets",
"Current assets"), and at least MIN_ROWS rows that have a text label. Chart axis ticks, which
extraction also turns into lines of bare numbers, have no label and don't count. A table's
header is the title and column lines above its first data row.

Known gap: text-only tables, such as NIST's category tables, have no figures and aren't found.
"""

import re
from dataclasses import dataclass

from .base import count_tokens

VERSION = "tables-1"

MIN_ROWS = 3  # labelled rows needed; fewer is prose with numbers, not a table
MAX_GAP_LINES = 2  # label lines allowed between rows inside one table
MAX_TITLE_LINES = 6  # lines above the table that may be its title
MAX_HEADER_TOKENS = 150  # header context added to continuation chunks is capped

_NUMBER = re.compile(r"^[(\-−]?[$€£]?\d[\d,]*(\.\d+)?%?\)?$|^\d+(\.\d+)?[–-]\d+(\.\d+)?$")
_FILLER = {"$", "%", "—", "–", "-", "±", "€", "£", "(", ")", "*"}
_YEAR = re.compile(r"^(19|20)\d\d$")
_CAPTION = re.compile(r"^(Table|TABLE)\s+\d+")
_SENTENCE_END = re.compile(r"[.!?:]\s*$")


@dataclass(frozen=True)
class Table:
    start: int  # title or first header line
    end: int  # end of the last row (or caption below it)
    header_end: int  # start of the first data row; [start, header_end) is the header


def _row_numbers(line: str) -> list[str] | None:
    """The trailing figures of a table row, or None if the line isn't a row."""
    words = line.split()
    numbers: list[str] = []
    for word in reversed(words):
        if _NUMBER.match(word):
            numbers.append(word)
        elif word not in _FILLER:
            break
    return numbers if len(numbers) >= 2 else None


def _is_labelled(line: str) -> bool:
    """A row with words before its figures. Chart axis ticks ("10 −4") have none."""
    numbers = _row_numbers(line) or []
    words = line.split()[: len(line.split()) - len(numbers)]
    return any(sum(ch.isalpha() for ch in word) >= 3 for word in words)


def _is_year_header(numbers: list[str]) -> bool:
    return all(_YEAR.match(n) for n in numbers)


def _lines(text: str) -> list[tuple[int, int]]:
    spans, position = [], 0
    for line in text.split("\n"):
        spans.append((position, position + len(line)))
        position += len(line) + 1
    return spans


def find_tables(text: str) -> list[Table]:
    lines = _lines(text)
    is_row = [_row_numbers(text[s:e]) is not None for s, e in lines]
    tables: list[Table] = []
    i = 0
    while i < len(lines):
        if not is_row[i]:
            i += 1
            continue
        first = last = i
        rows = int(_is_labelled(text[slice(*lines[i])]))
        j = i + 1
        while j < len(lines):
            if is_row[j]:
                last = j
                rows += _is_labelled(text[slice(*lines[j])])
            elif j - last > MAX_GAP_LINES or not text[lines[j][0] : lines[j][1]].strip():
                break
            j += 1
        if rows >= MIN_ROWS:
            tables.append(_build(text, lines, is_row, first, last))
        i = last + 1
    return tables


def _build(text, lines, is_row, first, last) -> Table:
    # First data row: the first row whose figures aren't just column years.
    data = first
    while data <= last and (
        not is_row[data] or _is_year_header(_row_numbers(text[slice(*lines[data])]) or [])
    ):
        data += 1
    # Title: short run of lines above, stopping at a blank line, another row, or prose.
    # A "Table N" line is the title's first line, so nothing above it is taken.
    top = first
    for k in range(first - 1, max(first - 1 - MAX_TITLE_LINES, -1), -1):
        line = text[lines[k][0] : lines[k][1]]
        if not line.strip() or is_row[k] or _SENTENCE_END.search(line):
            break
        top = k
        if _CAPTION.match(line):
            break
    # A caption directly below ("Table 1: ..."), as papers print it, belongs to the table.
    bottom = last
    if last + 1 < len(lines) and _CAPTION.match(text[slice(*lines[last + 1])]):
        bottom = last + 1
        while bottom + 1 < len(lines) and bottom - last < 3:
            if _SENTENCE_END.search(text[slice(*lines[bottom])]):
                break
            bottom += 1
    start, header_end = lines[top][0], lines[min(data, last)][0]
    return Table(start=start, end=lines[bottom][1], header_end=max(header_end, start))


def header_context(text: str, table: Table) -> tuple[int, int] | None:
    """The table's header range, trimmed from the top to fit MAX_HEADER_TOKENS."""
    start, end = table.start, table.header_end
    if end <= start:
        return None
    while count_tokens(text[start:end]) > MAX_HEADER_TOKENS:
        newline = text.find("\n", start, end)
        if newline < 0:
            return None
        start = newline + 1
    return (start, end) if text[start:end].strip() else None
