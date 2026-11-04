"""Pick the part of a document the optimizer tests on, and where its questions come from.

Short documents are used in full. Longer ones contribute evenly spaced windows covering about
25% of their tokens, capped at 30,000. Windows start and end on line boundaries and never cut
through a detected table. Sampled scores run high (fewer distractors), so they are only for
comparing candidates, not a measure of final quality.
"""

import math

from adaptive_rag.chunking import count_tokens, find_tables
from adaptive_rag.chunking.base import _encoding
from adaptive_rag.loaders import ExtractedDocument

FULL_DOCUMENT_TOKENS = 30_000
SAMPLE_SHARE = 0.25
SAMPLE_CAP_TOKENS = 30_000
WINDOW_TOKENS = 1_500
QUESTION_WINDOW_CHARS = 1_600
TABLE_QUESTION_MIN = 3  # when tables are more than TABLE_MIN_SHARE of the sample
TABLE_MIN_SHARE = 0.05
QUESTION_TYPES = ("factual", "conceptual", "multi_part")


SNAP_CHARS = 400  # snap to a line boundary only this close; otherwise to a word boundary
PER_TABLE_QUESTIONS = 3


def _line_start(text: str, position: int) -> int:
    line = text.rfind("\n", 0, position) + 1
    if position - line <= SNAP_CHARS:
        return line
    return text.rfind(" ", 0, position) + 1


def _line_end(text: str, position: int) -> int:
    end = text.find("\n", position)
    end = len(text) if end < 0 else end
    if end - position <= SNAP_CHARS:
        return end
    space = text.find(" ", position)
    return len(text) if space < 0 else space


def sample_regions(
    doc: ExtractedDocument,
    share: float = SAMPLE_SHARE,
    cap_tokens: int = SAMPLE_CAP_TOKENS,
) -> list[tuple[int, int]]:
    text = doc.text
    tokens = _encoding.encode_ordinary(text)
    if len(tokens) <= FULL_DOCUMENT_TOKENS:
        return [(0, len(text))]
    _, offsets = _encoding.decode_with_offsets(tokens)
    target = min(cap_tokens, int(share * len(tokens)))
    count = max(1, math.ceil(target / WINDOW_TOKENS))
    step = (len(tokens) - WINDOW_TOKENS) / max(count - 1, 1)
    tables = find_tables(text)
    regions: list[tuple[int, int]] = []
    for index in range(count):
        first = int(index * step)
        last = min(first + WINDOW_TOKENS, len(tokens) - 1)
        start = _line_start(text, offsets[first])
        end = _line_end(text, offsets[last])
        for table in tables:  # widen, never cut a table in half
            if table.start < start < table.end:
                start = table.start
            if table.start < end < table.end:
                end = table.end
        if regions and start <= regions[-1][1]:
            regions[-1] = (regions[-1][0], max(end, regions[-1][1]))
        else:
            regions.append((start, end))
    return regions


def question_plan(
    doc: ExtractedDocument, regions: list[tuple[int, int]], count: int
) -> list[tuple[int, int, str]]:
    """Windows (start, end, type) for question generation, spread across the regions.

    Table questions are planned in proportion to the sample's table share, with at least
    TABLE_QUESTION_MIN when tables are more than TABLE_MIN_SHARE of it.
    """
    text = doc.text
    tables = [t for t in find_tables(text) if any(s <= t.start and t.end <= e for s, e in regions)]
    sample_tokens = sum(count_tokens(text[s:e]) for s, e in regions)
    table_tokens = sum(count_tokens(text[t.start : t.end]) for t in tables)
    share = table_tokens / sample_tokens if sample_tokens else 0.0
    table_count = round(count * share)
    if share > TABLE_MIN_SHARE:
        table_count = max(table_count, TABLE_QUESTION_MIN)
    table_count = min(table_count, len(tables) * PER_TABLE_QUESTIONS, count)

    plan: list[tuple[int, int, str]] = []
    for i in range(table_count):
        if table_count <= len(tables):  # one question per table, spread over the tables
            table, start = tables[(i * len(tables)) // table_count], None
        else:  # every table once, then again a third and two thirds of the way down its rows
            table, depth = tables[i % len(tables)], i // len(tables)
            point = table.start + depth * (table.end - table.start) // PER_TABLE_QUESTIONS
            start = None if depth == 0 else _line_start(text, point)
        start = table.start if start is None else start
        plan.append((start, min(table.end, start + QUESTION_WINDOW_CHARS), "table"))

    others = count - table_count
    total = sum(e - s for s, e in regions)
    for i in range(others):
        # Position i of `others`, spread evenly over the concatenated regions.
        offset = int((i + 0.5) * total / others) if others else 0
        for s, e in regions:
            if offset < e - s:
                start = max(
                    s, min(s + offset - QUESTION_WINDOW_CHARS // 2, e - QUESTION_WINDOW_CHARS)
                )
                plan.append((start, min(e, start + QUESTION_WINDOW_CHARS), QUESTION_TYPES[i % 3]))
                break
            offset -= e - s
    return sorted(plan)
