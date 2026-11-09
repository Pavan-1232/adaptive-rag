"""Stage 5b parsers (adaptive_rag/structure.py) on made-up layouts: ICAI-style and generic."""

from adaptive_rag.loaders.base import Unit
from adaptive_rag.structure import (
    chapter_of,
    key,
    page_offset,
    parse_contents,
    parse_references,
)


def paged(*pages: str) -> tuple[str, list[Unit]]:
    """Canonical text and page units, like the PDF loader produces."""
    text, units, position = "", [], 0
    for number, page in enumerate(pages, start=1):
        chunk = page.strip("\n") + "\n"
        units.append(Unit(number, position, position + len(chunk)))
        text += chunk
        position += len(chunk)
    return text, units


BOOK = paged(
    "Book of Questions\n"
    "No. Chapter No. of Qs Page number\n"
    "1 Introduction to Standards 3 2 - 3\n"
    "2 Framework for Reports 2 4 - 4\n"
    "4.5 AS 20 · Earnings Per Share 4 5 - 6\n"
    "15 Branch Accounts 2 7 - 7\n"
    "Mix Mixed-topic case scenarios 6 8 - 9\n",
    "Introduction to Standards\nQuestion index\n"
    "01 RTP - May 2025, Q.5\n02 ICAI SM - 1 Basics of Standards, TYK Q.1\n"
    "01 RTP - May 2025, Q.5 Notebook Page No.\nWhat is the role of standards?\n",
    "02 ICAI SM - 1 Basics of Standards, TYK Q.1 Notebook Page No.\nWho issues standards?\n",
    "Framework for Reports\nSome text.\n",
    "AS 20 · Earnings Per Share\n"
    "01 PYQ - Nov 2024, Q.2(a) 5 marks Notebook Page No.\nCompute EPS.\n",
)


def test_contents_rows_with_printed_counts_and_header():
    rows = parse_contents(*BOOK)
    assert [(r.label, r.title, r.count, r.page_start, r.page_end) for r in rows] == [
        ("1", "Introduction to Standards", 3, 2, 3),
        ("2", "Framework for Reports", 2, 4, 4),
        ("4.5", "AS 20 · Earnings Per Share", 4, 5, 6),
        ("15", "Branch Accounts", 2, 7, 7),
        ("Mix", "Mixed-topic case scenarios", 6, 8, 9),
    ]
    assert rows[0].header == "No. Chapter No. of Qs Page number"
    assert {r.locator for r in rows} == {1}


def test_source_references_index_lines_headers_and_chapters():
    text, units = BOOK
    rows = parse_contents(text, units)
    refs = parse_references(text, units, rows)
    assert [(r.label, r.short_key, r.entry, r.is_header, r.locator) for r in refs] == [
        ("RTP - May 2025, Q.5", "rtp may 2025 q 5", 1, False, 2),
        ("ICAI SM - 1 Basics of Standards, TYK Q.1", "tyk q 1", 2, False, 2),
        ("RTP - May 2025, Q.5", "rtp may 2025 q 5", 1, True, 2),
        ("ICAI SM - 1 Basics of Standards, TYK Q.1", "tyk q 1", 2, True, 3),
        ("PYQ - Nov 2024, Q.2(a)", "pyq nov 2024 q 2 a", 1, True, 5),
    ]
    offset = page_offset(text, rows, units)
    assert offset == 0  # titles reappear on their printed pages
    assert [chapter_of(rows, offset, r.locator) for r in refs] == ["1", "1", "1", "1", "4.5"]


def test_index_lines_ending_in_a_digit_are_not_contents_rows():
    text, units = paged(
        "01 ICAI SM - 1 Basics of Standards, TYK Q.1\n02 ICAI SM - 1 Basics of Standards, TYK Q.2\n"
        "03 ICAI SM - 1 Basics of Standards, TYK Q.3\n04 ICAI SM - 1 Basics of Standards, TYK Q.4\n"
        "05 ICAI SM - 1 Basics of Standards, TYK Q.5\n"
    )
    assert parse_contents(text, units) == []
    assert len(parse_references(text, units)) == 5


TEN_K = paged(
    "Table of Contents\nPage\n"
    "Item 1. Business 4\nItem 1A. Risk Factors 13\nItem 1B. Unresolved Staff Comments 27\n"
    "Item 2. Properties 28\nItem 7. Management's Discussion and Analysis 31\n",
    "ITEM 1A. RISK FACTORS\nOur business faces risks.\n"
    "Total revenues 97,690 96,773 81,462\nCost of revenues 80,240 79,113 60,609\n"
    "Gross profit 17,450 17,660 20,853\n"
    "As shown in Table 2 below, margins fell.\n"
    "Table 2 Segment margins\n",
    "List of tables\nTable 1 Revenue by segment 21\nTable 2 Segment margins 22\n"
    "Table 3 Cash flows 23\n",
)


def test_generic_contents_and_labels():
    text, units = TEN_K
    rows = parse_contents(text, units)
    assert [(r.label, r.title, r.count, r.page_start) for r in rows][:2] == [
        ("Item 1", "Business", None, 4),
        ("Item 1A", "Risk Factors", None, 13),
    ]
    refs = parse_references(text, units, rows)
    headers = [(r.kind, r.label, r.locator) for r in refs if r.is_header]
    # The heading in the body and the caption count; contents lines don't become references.
    assert ("item", "Item 1A", 2) in headers and ("table", "Table 2", 2) in headers
    assert all(r.locator != 1 for r in refs)


def test_generic_documents_are_not_harmed():
    text, units = TEN_K
    rows = parse_contents(text, units)
    # Financial rows have no label and comma figures: never contents rows.
    assert all("revenues" not in r.title.lower() for r in rows)
    refs = parse_references(text, units, rows)
    # A mid-sentence mention isn't a label; a list of tables isn't the captions themselves.
    assert not any(r.label == "Table 2" and r.locator == 2 and not r.is_header for r in refs)
    listed = [r for r in refs if r.locator == 3]
    assert len(listed) == 3 and not any(r.is_header for r in listed)
    prose = paged("This paper studies retrieval. Section 4 compares methods on 3 datasets.\n")
    assert parse_contents(*prose) == [] and parse_references(*prose) == []


def test_key_normalizes_punctuation_and_case():
    assert key("RTP - Nov 2023, Q.2") == "rtp nov 2023 q 2"
    assert key("ITEM 1A.") == "item 1a"
