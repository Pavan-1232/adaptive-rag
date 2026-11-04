"""Recursive (C2–C4) and table-aware (C7) chunkers, and the table detector they rely on."""

import pytest

from adaptive_rag.chunking import (
    chunk_recursive,
    chunk_table_aware,
    count_tokens,
    embedding_text,
    find_tables,
)
from adaptive_rag.chunking.tables import MAX_HEADER_TOKENS, header_context
from adaptive_rag.loaders import ExtractedDocument, Section, Unit


def doc_from_text(text: str, sections=()) -> ExtractedDocument:
    units, offset = [], 0
    for number, line in enumerate(text.split("\n"), start=1):
        units.append(Unit(number, offset, offset + len(line)))
        offset += len(line) + 1
    return ExtractedDocument(text, "line", units, list(sections))


def prose(paragraphs=40, sentences=6) -> str:
    return "\n\n".join(
        " ".join(
            f"Paragraph {p} sentence {s} discusses quarterly revenue." for s in range(sentences)
        )
        for p in range(paragraphs)
    )


TABLE = "\n".join(
    [
        "Consolidated Statements of Operations",
        "(in millions)",
        "2024 2023 2022",
        "Automotive sales $ 72,480 $ 78,509 $ 67,210",
        "Automotive regulatory credits 2,763 1,790 1,776",
        "Automotive leasing 1,827 2,120 2,476",
        "Total revenues 97,690 96,773 81,462",
    ]
)


def big_table(rows=120) -> str:
    lines = ["Table 1. Segment results by quarter", "(in millions)", "2024 2023 2022"]
    lines += [f"Segment line item {i} revenue {i},101 {i},202 ({i},303)" for i in range(rows)]
    return "\n".join(lines)


def assert_offsets(doc, chunks, size):
    for i, chunk in enumerate(chunks):
        assert chunk.index == i
        assert doc.text[chunk.start : chunk.end] == chunk.text
        assert chunk.token_count == count_tokens(chunk.text) <= size
        assert chunk.text == chunk.text.strip()


def covered(doc, chunks) -> bool:
    """Every non-whitespace character is inside some chunk."""
    inside = [False] * len(doc.text)
    for chunk in chunks:
        inside[chunk.start : chunk.end] = [True] * (chunk.end - chunk.start)
    return all(inside[i] or ch.isspace() for i, ch in enumerate(doc.text))


# ---------------------------------------------------------------- recursive


@pytest.mark.parametrize(("size", "overlap"), [(256, 25), (512, 50), (1024, 100), (64, 0)])
def test_recursive_offsets_sizes_and_coverage(size, overlap):
    doc = doc_from_text(prose())
    chunks = chunk_recursive(doc, size, overlap)
    assert len(chunks) > 1
    assert_offsets(doc, chunks, size)
    assert covered(doc, chunks)


def test_recursive_offsets_hold_for_multibyte_text():
    doc = doc_from_text("\n\n".join("Café — naïve résumé 価格は上昇した。" * 8 for _ in range(30)))
    chunks = chunk_recursive(doc, 128, 10)
    assert_offsets(doc, chunks, 128)
    assert covered(doc, chunks)


def test_recursive_prefers_paragraph_boundaries():
    doc = doc_from_text(prose(paragraphs=30, sentences=3))
    starts = {0} | {i + 2 for i in range(len(doc.text)) if doc.text.startswith("\n\n", i)}
    assert all(chunk.start in starts for chunk in chunk_recursive(doc, 256, 0))


def test_recursive_overlap_is_bounded_and_zero_means_none():
    doc = doc_from_text(prose(sentences=12))
    chunks = chunk_recursive(doc, 256, 40)
    shared = [max(0, a.end - b.start) for a, b in zip(chunks, chunks[1:], strict=False)]
    assert any(shared)
    for a, b in zip(chunks, chunks[1:], strict=False):
        if a.end > b.start:
            assert count_tokens(doc.text[b.start : a.end]) <= 40
        assert b.start > a.start  # always makes progress
    no_overlap = chunk_recursive(doc, 256, 0)
    assert all(a.end <= b.start for a, b in zip(no_overlap, no_overlap[1:], strict=False))


def test_recursive_splits_a_line_without_separators_by_tokens():
    doc = doc_from_text("x" * 20000)
    chunks = chunk_recursive(doc, 100, 0)
    assert_offsets(doc, chunks, 100)
    assert covered(doc, chunks)


def test_recursive_records_sections_and_locators():
    text = prose(paragraphs=10)
    middle = len(text) // 2
    doc = doc_from_text(text, [Section("Intro", 0, middle), Section("Results", middle, len(text))])
    chunks = chunk_recursive(doc, 128, 0)
    assert chunks[0].section_heading == "Intro"
    assert chunks[-1].section_heading == "Results"
    assert all(c.locator_start <= c.locator_end for c in chunks)


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (2000, 0), (100, 100), (100, -1)])
def test_recursive_rejects_invalid_settings(size, overlap):
    with pytest.raises(ValueError):
        chunk_recursive(doc_from_text("text"), size, overlap)


# ---------------------------------------------------------------- table detection


def test_finds_a_financial_table_with_title_and_year_header():
    text = "Revenue grew this year.\n\n" + TABLE + "\n\nMore prose follows here."
    [table] = find_tables(text)
    assert text[table.start :].startswith("Consolidated Statements of Operations")
    assert text[table.start : table.end].endswith("Total revenues 97,690 96,773 81,462")
    assert text[table.header_end :].startswith("Automotive sales")


def test_title_search_stops_at_prose_and_at_a_table_caption():
    text = "a line of prose that runs on without stopping\nTable 3. Results\n" + TABLE
    [table] = find_tables(text)
    assert text[table.start :].startswith("Table 3. Results")
    text = "The paragraph ends here.\n" + TABLE
    [table] = find_tables(text)
    assert text[table.start :].startswith("Consolidated")


def test_chart_axis_ticks_and_prose_with_numbers_are_not_tables():
    axis = "\n".join(["40", "2", "30 0", "20 −2", "10 −4", "0 −6", "2019 2020 2021 2022 2023"])
    sentences = "\n".join(
        [
            "Revenue rose in 2024 and 2023.",
            "Costs were $5 million in 2022.",
            "Margins improved from 18.9% to 26.2%",
            "Deliveries reached 1.79 million.",
        ]
    )
    assert find_tables(axis) == []
    assert find_tables(sentences) == []


def test_caption_below_a_paper_table_is_included():
    text = "Faith. Ans. Rel. Cont. Rel.\nRagas 0.95 0.78 0.70\nGPT Score 0.72 0.52 0.63\n"
    text += "GPT Ranking 0.54 0.40 0.52\nTable 1: Agreement with human annotators.\nBody text."
    [table] = find_tables(text)
    assert text[table.start : table.end].endswith("Table 1: Agreement with human annotators.")


def test_header_context_is_capped():
    title = "\n".join(f"Long title line {i} " + "word " * 30 for i in range(6))
    text = title + "\n2024 2023\n" + "\n".join(f"Item {i} {i},000 {i},500" for i in range(5))
    [table] = find_tables(text)
    start, end = header_context(text, table)
    assert count_tokens(text[start:end]) <= MAX_HEADER_TOKENS
    assert text[start:end].endswith("2024 2023\n")  # the column line nearest the rows is kept


# ---------------------------------------------------------------- C7


def test_small_table_is_one_chunk_with_its_title():
    doc = doc_from_text(prose(paragraphs=6) + "\n\n" + TABLE + "\n\n" + prose(paragraphs=6))
    chunks = chunk_table_aware(doc, 512, 50)
    tables = [c for c in chunks if c.is_table]
    assert len(tables) == 1
    assert tables[0].text == TABLE
    assert tables[0].context_start is None
    assert_offsets(doc, chunks, 512)
    assert covered(doc, chunks)


def test_prose_chunks_never_cross_into_a_table():
    doc = doc_from_text(prose(paragraphs=6) + "\n\n" + TABLE + "\n\n" + prose(paragraphs=6))
    [table] = find_tables(doc.text)
    for chunk in chunk_table_aware(doc, 256, 25):
        inside = table.start <= chunk.start and chunk.end <= table.end
        outside = chunk.end <= table.start or chunk.start >= table.end
        assert inside if chunk.is_table else outside


def test_large_table_splits_only_between_rows_and_carries_its_header():
    body = big_table()
    doc = doc_from_text("Intro paragraph.\n\n" + body + "\n\nClosing paragraph.")
    [table] = find_tables(doc.text)
    pieces = [c for c in chunk_table_aware(doc, 256, 25) if c.is_table]
    assert len(pieces) > 2
    assert pieces[0].context_start is None
    assert pieces[0].text.startswith("Table 1. Segment results")
    header = doc.text[table.start : table.header_end]
    for piece in pieces:
        assert piece.start == table.start or doc.text[piece.start - 1] == "\n"
        assert piece.end == table.end or doc.text[piece.end] == "\n"
    for piece in pieces[1:]:
        context = doc.text[piece.context_start : piece.context_end]
        assert context == header
        assert count_tokens(embedding_text(doc.text, piece)) <= 256 + 1
    rows = "\n".join(p.text for p in pieces)
    assert rows == doc.text[table.start : table.end]  # nothing lost or repeated


def test_an_over_long_row_falls_back_to_splitting_inside_it():
    row = "Line item " + " ".join(f"{i},000" for i in range(400))
    doc = doc_from_text("Results\n2024 2023\n" + "\n".join([row, "A 1,0 2,0", "B 3,0 4,0"]))
    chunks = chunk_table_aware(doc, 128, 0)
    assert_offsets(doc, chunks, 128)
    assert covered(doc, chunks)


def test_without_tables_c7_matches_recursive():
    doc = doc_from_text(prose())
    c7 = [(c.start, c.end) for c in chunk_table_aware(doc, 512, 50)]
    assert c7 == [(c.start, c.end) for c in chunk_recursive(doc, 512, 50)]


def test_embedding_text_is_the_chunk_without_context():
    doc = doc_from_text(TABLE)
    [chunk] = chunk_table_aware(doc)
    assert embedding_text(doc.text, chunk) == chunk.text
