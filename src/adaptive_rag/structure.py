"""Document structure for exact lookups (Stage 5b, 2026-11-09): contents rows and reference labels.

PDF extraction keeps a table row or a question header on one line ("7 AS 19 · Leases 12 40 - 44",
"03 RTP - Nov 2023, Q.2 Notebook Page No."), but chunking packs dozens of near-identical rows
together and search can't single one out. These parsers read the canonical
text line by line, with plain rules and no new dependency, and return records that are stored in
SQLite and matched exactly at query time (retrieval/lookup.py).

All layout patterns live in this module, so other layouts can be added here:
- CONTENTS: a run of rows "<label> <title> [<count>] <page>[ - <page>]" with rising pages, e.g.
  a book's chapter index or a 10-K's "Item 1A. Risk Factors 13".
- REFERENCE labels at the start of a line: ICAI-style source headers ("03 RTP - Nov 2023, Q.2",
  "01 ICAI SM - 1 Basics of Standards, TYK Q.1") and generic captions and headings ("Table 2",
  "Illustration 3", "Question 14", "Item 1A", "Section 4.2").
Counts are only ever the numbers printed in a row; nothing is counted by code.
"""

import re
from collections import Counter
from dataclasses import dataclass

VERSION = "structure-1"

# ---------------------------------------------------------------- patterns (one place)

_CONTENTS_LABEL = re.compile(
    r"^(?P<label>\d{1,2}(?:\.\d{1,2}){0,2}|Mix|Item\s+\d{1,2}[A-Z]?|Part\s+[IVX]+|"
    r"Chapter\s+\d{1,2}|Appendix\s+[A-Z0-9]{1,2}|[IVX]{1,4})\.?\s+(?P<rest>.+)$"
)
_TRAILING_PAGES = re.compile(
    r"^(?P<title>.*?[A-Za-z].*?)[\s.·…]+(?:(?P<count>\d{1,4})\s+)?(?P<start>\d{1,4})"
    r"(?:\s*[-–]\s*(?P<end>\d{1,4}))?$"
)
_HEADER_HINT = re.compile(r"\b(?:page|pages|chapter|contents|no\.|qs)\b", re.IGNORECASE)
MIN_CONTENTS_ROWS = 5  # fewer is not an index
MAX_GAP_LINES = 1  # non-row lines allowed inside a contents block (a wrapped title)

# ICAI study material and the question books built on it.
_SOURCE_HEADER = re.compile(
    r"^(?P<entry>\d{1,3})\s+(?P<ref>(?:ICAI SM|RTP|MTP|PYQ|Model Test Paper)\b.*?)"
    r"(?P<tail>\s+(?:\d+\s+marks\s*)?Notebook Page No\.?)?\s*$"
)
# Generic captions and headings at the start of a line.
_LABEL = re.compile(
    r"^(?P<kind>Table|Figure|Fig\.|Illustration|Example|Question|Exhibit|Appendix|Annex|"
    r"Section|Item)\s+(?P<number>[A-Z]?\d{1,3}[A-Z]?(?:\.\d{1,2}){0,2})\b",
    re.IGNORECASE,  # "ITEM 1A." and "ILLUSTRATION 3" headings
)
_SHORT_REF = re.compile(
    r"\b(?:TYK Q\.?\s*\d+|Illustration\s+\d+|Q\.?\s*\d+(?:\([a-z]\))?)", re.IGNORECASE
)


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def key(text: str) -> str:
    """Normalized form used for exact matching: lower-case words and numbers."""
    return " ".join(words(text))


# ---------------------------------------------------------------- records


@dataclass(frozen=True)
class ContentsRow:
    label: str
    title: str
    count: int | None  # only when printed in the row
    page_start: int  # as printed
    page_end: int | None
    header: str | None  # the column header line above the block, if any
    char_start: int
    char_end: int
    locator: int  # where the row itself is (page, or line/paragraph for non-PDF)


@dataclass(frozen=True)
class Reference:
    kind: str  # "source" (ICAI-style source header or index row) or a caption kind: "table"...
    label: str  # as printed: "RTP - Nov 2023, Q.2", "Table 2"
    key: str  # key(label)
    short_key: str  # the part users quote: "rtp nov 2023 q 2", "tyk q 7", "table 2"
    entry: int | None  # the book's running number ("04")
    is_header: bool  # the question or caption itself (not a line in an index)
    char_start: int
    char_end: int
    locator: int


# ---------------------------------------------------------------- parsing


def _lines(text: str) -> list[tuple[int, int, str]]:
    out, position = [], 0
    for line in text.split("\n"):
        out.append((position, position + len(line), line.strip()))
        position += len(line) + 1
    return out


def _locator(units, position: int) -> int:
    for unit in units:
        if unit.start <= position < max(unit.end, unit.start + 1):
            return unit.number
    return units[-1].number if units else 1


def _contents_row(line: str):
    if _SOURCE_HEADER.match(line):
        return None  # "01 ICAI SM - ..., TYK Q.1" ends in a digit but is a reference, not a page
    match = _CONTENTS_LABEL.match(line)
    if not match:
        return None
    pages = _TRAILING_PAGES.match(match["rest"])
    if not pages:
        return None
    title = pages["title"].strip(" .·…")
    if sum(ch.isalpha() for ch in title) < 3:
        return None
    end = int(pages["end"]) if pages["end"] else None
    count = int(pages["count"]) if pages["count"] and end is not None else None
    if pages["count"] and end is None:
        title = f"{title} {pages['count']}"  # "Title 2 13": no range, so 2 belongs to the title
    start = int(pages["start"])
    if end is not None and end < start:
        return None
    return match["label"], title, count, start, end


def parse_contents(text: str, units) -> list[ContentsRow]:
    lines = _lines(text)
    rows: list[ContentsRow] = []
    block: list[tuple[int, tuple]] = []  # (line index, parsed)

    def flush():
        starts = [parsed[3] for _, parsed in block]
        if len(block) >= MIN_CONTENTS_ROWS and starts == sorted(starts):
            first = block[0][0]
            header = None
            for back in (1, 2):
                if first - back >= 0 and _HEADER_HINT.search(lines[first - back][2]):
                    header = lines[first - back][2]
                    break
            for index, (label, title, count, start, end) in block:
                s, e, _ = lines[index]
                rows.append(
                    ContentsRow(label, title, count, start, end, header, s, e, _locator(units, s))
                )
        block.clear()

    gap = 0
    for index, (_, _, line) in enumerate(lines):
        parsed = _contents_row(line)
        if parsed:
            block.append((index, parsed))
            gap = 0
        elif block and line and gap < MAX_GAP_LINES:
            gap += 1
        else:
            flush()
            gap = 0
    flush()
    return rows


def parse_references(
    text: str, units, contents: list[ContentsRow] | None = None
) -> list[Reference]:
    """Reference labels. Lines that are contents rows are skipped, and a caption-like line in a
    run of three or more that end in a page number ("Table 2 ... 21", a list of tables) is an
    index entry, not the caption itself (is_header False)."""
    taken = {row.char_start for row in contents or []}
    contents_pages = {row.locator for row in contents or []}
    lines = _lines(text)
    listing = _listing_lines(lines)
    found: list[Reference] = []
    for index, (start, end, line) in enumerate(lines):
        if not line or start in taken:
            continue
        source = _SOURCE_HEADER.match(line)
        if source:
            label = source["ref"].strip()
            short = _SHORT_REF.findall(label)
            short_key = key(short[-1]) if short else key(label)
            if label.startswith(("RTP", "MTP", "PYQ", "Model Test Paper")):
                short_key = key(label)  # "rtp nov 2023 q 2": the whole reference is short
            found.append(
                Reference(
                    "source",
                    label,
                    key(label),
                    short_key,
                    int(source["entry"]),
                    bool(source["tail"]),
                    start,
                    end,
                    _locator(units, start),
                )
            )
            continue
        caption = _LABEL.match(line)
        if caption:
            kind = caption["kind"].rstrip(".").lower()
            kind = "figure" if kind.startswith("fig") else kind
            label = f"{kind.capitalize()} {caption['number']}"
            on_contents_page = _locator(units, start) in contents_pages
            found.append(
                Reference(
                    kind,
                    label,
                    key(label),
                    key(f"{kind} {caption['number']}"),
                    None,
                    index not in listing and not on_contents_page,
                    start,
                    end,
                    _locator(units, start),
                )
            )
    return found


_ENDS_IN_PAGE = re.compile(r"[\s.·…]\d{1,4}$")


def _listing_lines(lines) -> set[int]:
    """Indexes of caption-like lines that sit in a run of 3+ lines ending in a page number."""
    flags = [bool(_LABEL.match(line) and _ENDS_IN_PAGE.search(line)) for _, _, line in lines]
    listing: set[int] = set()
    run: list[int] = []
    for index, flag in enumerate([*flags, False]):
        if flag:
            run.append(index)
            continue
        if len(run) >= 3:
            listing.update(run)
        run = []
    return listing


def page_offset(text: str, rows: list[ContentsRow], units) -> int | None:
    """Physical page minus printed page, from where the titles reappear after the index.
    None without a clear majority (then chapters aren't assigned)."""
    if not rows:
        return None
    after = max(r.char_end for r in rows)
    lines = [(s, line) for s, _, line in _lines(text) if s > after and line]
    votes: Counter[int] = Counter()
    for row in rows:
        target = key(row.title)
        if len(target) < 6:
            continue
        for start, line in lines:
            if key(line) == target or (len(target) > 15 and target in key(line)):
                votes[_locator(units, start) - row.page_start] += 1
                break
    if not votes:
        return None
    offset, count = votes.most_common(1)[0]
    return offset if count >= max(2, len(rows) // 3) else None


def chapter_of(rows: list[ContentsRow], offset: int | None, locator: int) -> str | None:
    """The contents label whose printed page range holds this physical page."""
    if offset is None:
        return None
    printed = locator - offset
    best = None
    for row in rows:
        if row.page_start <= printed <= (row.page_end or row.page_start):
            if best is None or row.page_start >= best.page_start:
                best = row
    return best.label if best else None


# ---------------------------------------------------------------- storage


def save_structure(conn, document_id: int, text: str, units) -> tuple[int, int]:
    """Parse and store one document's structure, replacing what was there. Returns counts."""
    rows = parse_contents(text, units)
    refs = parse_references(text, units, rows)
    offset = page_offset(text, rows, units)
    conn.execute("DELETE FROM doc_contents WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM doc_references WHERE document_id = ?", (document_id,))
    conn.executemany(
        "INSERT INTO doc_contents (document_id, label, title, title_key, question_count,"
        " page_start, page_end, header, char_start, char_end, locator, page_offset)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                document_id,
                r.label,
                r.title,
                key(r.title),
                r.count,
                r.page_start,
                r.page_end,
                r.header,
                r.char_start,
                r.char_end,
                r.locator,
                offset,
            )
            for r in rows
        ],
    )
    conn.executemany(
        "INSERT INTO doc_references (document_id, kind, label, ref_key, short_key, entry,"
        " is_header, chapter, char_start, char_end, locator)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                document_id,
                r.kind,
                r.label,
                r.key,
                r.short_key,
                r.entry,
                int(r.is_header),
                chapter_of(rows, offset, r.locator),
                r.char_start,
                r.char_end,
                r.locator,
            )
            for r in refs
        ],
    )
    conn.execute("UPDATE documents SET structure_version = ? WHERE id = ?", (VERSION, document_id))
    return len(rows), len(refs)


def backfill(conn) -> list[tuple[str, int, int]]:
    """Parse ready documents whose structure is missing or from an older parser, from the
    canonical text stored at upload (the same text the chunks were cut from)."""
    import json

    from adaptive_rag.loaders.base import Unit

    done = []
    pending = conn.execute(
        "SELECT id, filename, canonical_text, units FROM documents WHERE status = 'ready'"
        " AND canonical_text IS NOT NULL AND (structure_version IS NULL OR structure_version != ?)",
        (VERSION,),
    ).fetchall()
    for document_id, filename, text, units in pending:
        counts = save_structure(conn, document_id, text, [Unit(**u) for u in json.loads(units)])
        done.append((filename, *counts))
    return done
