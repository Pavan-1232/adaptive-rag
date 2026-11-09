"""Exact lookups (Stage 5b, 2026-11-09): contents rows and reference labels, matched exactly.

Opt-in (`structured_lookup`, off until measured), in both retrieval modes, after normal
retrieval and before answer-key linking. Matches come from doc_contents and doc_references
(adaptive_rag/structure.py), only for this knowledge base's ready documents, and are added as
the real chunks that hold them, marked "lookup", so citations point to real pages:
- a reference in the question ("RTP Nov 2023 Q.2", "Table 2", "Item 1A", "TYK Q.7"), narrowed
  by a chapter in the question; more than MAX_MATCHES candidates is ambiguous and skipped;
- a contents question ("which pages cover AS 20", "how many questions on ...") -> the row, with
  the index's column header as context when the chunk doesn't contain it;
- a listing question ("which questions cover ...") -> the chapter's printed question index.
Counts are only those printed in a row.
"""

import re
import sqlite3
from dataclasses import replace

from adaptive_rag.chunking.base import count_tokens
from adaptive_rag.context import AppContext
from adaptive_rag.structure import words

from .baseline import _CHUNK_SELECT, _to_chunk, ready_document_ids
from .types import RetrievedChunk

_CONTENTS = re.compile(
    r"\b(?:which pages?|what pages?|page ranges?|pages? (?:does|do|that)?\s*cover|"
    r"on which pages|how many questions|number of questions|no\.? of questions|"
    r"how many (?:[\w-]+ ){0,3}(?:cases|scenarios|questions|illustrations))\b",
    re.IGNORECASE,
)
_LISTING = re.compile(
    r"\b(?:which questions|list (?:the |all )?questions|what questions)\b", re.IGNORECASE
)
_CHAPTER = re.compile(r"\bchapter\s+(\d{1,2})(?:\s*,?\s*unit\s+(\d{1,2}))?", re.IGNORECASE)
_STANDARD = re.compile(r"\bas\s+(\d{1,2})\b", re.IGNORECASE)
MAX_MATCHES = 3  # more reference matches than this is ambiguous: skipped, never guessed
MAX_NGRAM = 8
_STOP = frozenset("the a an of in on to for and or is are what which how does do".split())


def add_lookups(
    ctx: AppContext, kb: sqlite3.Row, used: list[RetrievedChunk], question: str, max_tokens: int
) -> tuple[list[RetrievedChunk], dict]:
    documents = ready_document_ids(ctx, kb)
    info: dict = {"matches": [], "skipped": []}
    if not documents:
        return used, info
    found: list[tuple[str, RetrievedChunk]] = []
    with ctx.db() as conn:
        found += _references(conn, documents, question, info)
        if _LISTING.search(question):
            found += _listing(conn, documents, question, info)
        elif _CONTENTS.search(question):
            found += _contents(conn, documents, question, info)
    if not found:
        return used, info

    have = {piece.chunk_id for chunk in used for piece in chunk.pieces}
    top = max((c.score for c in used), default=1.0)
    added: list[RetrievedChunk] = []
    info["already"] = [c.chunk_id for _, c in found if c.chunk_id in have]  # search found them
    for _, chunk in found:
        if chunk.chunk_id in have:
            continue
        have.add(chunk.chunk_id)
        added.append(replace(chunk, score=top, source="lookup"))
    kept = list(used)
    while kept and _tokens(added + kept) > max_tokens:
        droppable = [c for c in kept if c.source not in ("lookup", "answer_key")]
        if not droppable:
            break
        kept.remove(min(droppable, key=lambda c: c.score))
    while added and _tokens(added + kept) > max_tokens:
        added.pop()
    info["added"] = [c.chunk_id for c in added]
    return added + kept, info


def _tokens(chunks: list[RetrievedChunk]) -> int:
    return sum(c.evidence_tokens for c in chunks)


def _chunk_number(conn, document_id: int, index: int) -> RetrievedChunk | None:
    row = conn.execute(
        _CHUNK_SELECT + "c.document_id = ? AND c.chunk_index = ?", (document_id, index)
    ).fetchone()
    return None if row is None else _to_chunk(row, 0.0)


def _chunk_at(conn, document_id: int, position: int) -> RetrievedChunk | None:
    row = conn.execute(
        _CHUNK_SELECT + "c.document_id = ? AND c.start_char <= ? AND c.end_char > ?"
        " ORDER BY c.chunk_index LIMIT 1",
        (document_id, position, position),
    ).fetchone()
    return None if row is None else _to_chunk(row, 0.0)


def _chapter_filter(question: str) -> str | None:
    match = _CHAPTER.search(question)
    if not match:
        return None
    return match[1] if not match[2] else f"{match[1]}.{match[2]}"


def _ngrams(question: str) -> set[str]:
    tokens = words(question)
    return {
        " ".join(tokens[i : i + n])
        for n in range(2, MAX_NGRAM + 1)
        for i in range(len(tokens) - n + 1)
    }


def _references(conn, documents: list[int], question: str, info: dict):
    grams = sorted(_ngrams(question))
    if not grams:
        return []
    marks = ",".join("?" * len(documents))
    rows = conn.execute(
        f"SELECT * FROM doc_references WHERE document_id IN ({marks})"  # noqa: S608
        f" AND short_key IN ({','.join('?' * len(grams))})",
        [*documents, *grams],
    ).fetchall()
    if not rows:
        return []
    chapter = _chapter_filter(question)
    if chapter:
        narrowed = [r for r in rows if (r["chapter"] or "") == chapter]
        rows = narrowed or rows
    asked = set(words(question))
    # Prefer the longest matched reference, then the one sharing most words with the question.
    longest = max(len(r["short_key"]) for r in rows)
    rows = [r for r in rows if len(r["short_key"]) == longest]
    best = max(len(asked & set(r["ref_key"].split())) for r in rows)
    rows = [r for r in rows if len(asked & set(r["ref_key"].split())) == best]
    headers = [r for r in rows if r["is_header"]] or rows
    if len(headers) > MAX_MATCHES:
        info["skipped"].append(
            {"kind": "reference", "key": rows[0]["short_key"], "candidates": len(headers)}
        )
        return []
    found = []
    for r in headers:
        chunk = _chunk_at(conn, r["document_id"], r["char_start"])
        if chunk is None:
            continue
        found.append(("reference", chunk))
        info["matches"].append(
            {
                "kind": "reference",
                "label": r["label"],
                "chunk": chunk.chunk_id,
                "page": r["locator"],
                "chapter": r["chapter"],
            }
        )
        if r["is_header"] and r["char_start"] > chunk.end_char - 400:
            # The question itself starts near the end of this chunk: add the next one too.
            following = _chunk_number(conn, r["document_id"], chunk.chunk_index + 1)
            if following is not None:
                found.append(("reference", following))
    return found


def _document_hint(conn, documents: list[int], question: str) -> dict[int, int]:
    """How well the question names each document, from its filename and the text above its
    contents ("Book of Questions"). Used only to break ties between documents."""
    asked = {w for w in words(question) if w not in _STOP}
    hints = {}
    for document_id in documents:
        doc = conn.execute(
            "SELECT d.filename, substr(d.canonical_text, 1, MIN(c.char_start)) AS head"
            " FROM documents d LEFT JOIN doc_contents c ON c.document_id = d.id"
            " WHERE d.id = ?",
            (document_id,),
        ).fetchone()
        text = f"{doc['filename']} {doc['head'] or ''}"
        hints[document_id] = len(asked & set(words(text)))
    return hints


def _contents_rows(conn, documents, question: str):
    marks = ",".join("?" * len(documents))
    # Only "?" placeholders are formatted in; all values are bound.
    sql = f"SELECT * FROM doc_contents WHERE document_id IN ({marks})"  # noqa: S608
    rows = conn.execute(sql, documents).fetchall()
    asked = {w for w in words(question) if w not in _STOP and len(w) > 2}
    standard = _STANDARD.search(question)
    scored = []
    for r in rows:
        title = set(r["title_key"].split())
        score = len(asked & title)
        if standard and f"as {standard[1]}" in r["title_key"]:
            score += 5
        if score >= 2:
            scored.append((score, r))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    top = [r for s, r in scored if s == best]
    if len({r["document_id"] for r in top}) > 1:
        hints = _document_hint(conn, list({r["document_id"] for r in top}), question)
        strongest = max(hints.values())
        if strongest > 0:
            top = [r for r in top if hints[r["document_id"]] == strongest]
    return top[:MAX_MATCHES]


def _contents(conn, documents, question: str, info: dict):
    found = []
    for r in _contents_rows(conn, documents, question):
        chunk = _chunk_at(conn, r["document_id"], r["char_start"])
        if chunk is None:
            continue
        header = r["header"]
        if header and header not in chunk.text:
            chunk = replace(chunk, context_text=header, context_tokens=count_tokens(header) + 1)
        found.append(("contents", chunk))
        info["matches"].append(
            {
                "kind": "contents",
                "label": r["label"],
                "title": r["title"],
                "count": r["question_count"],
                "chunk": chunk.chunk_id,
                "page": r["locator"],
            }
        )
    return found


def _listing(conn, documents, question: str, info: dict):
    """The chapter's printed question index: the first index lines inside its page range."""
    found = []
    for r in _contents_rows(conn, documents, question):
        if r["page_offset"] is None:
            continue
        first, last = (
            r["page_start"] + r["page_offset"],
            (r["page_end"] or r["page_start"]) + r["page_offset"],
        )
        entries = conn.execute(
            "SELECT * FROM doc_references WHERE document_id = ? AND is_header = 0"
            " AND locator BETWEEN ? AND ? ORDER BY char_start",
            (r["document_id"], first, last),
        ).fetchall()
        if not entries:
            continue
        chunk = _chunk_at(conn, r["document_id"], entries[0]["char_start"])
        if chunk is None:
            continue
        found.append(("listing", chunk))
        if entries[-1]["char_start"] >= chunk.end_char:  # the index runs on
            following = _chunk_number(conn, r["document_id"], chunk.chunk_index + 1)
            if following is not None:
                found.append(("listing", following))
        info["matches"].append(
            {
                "kind": "listing",
                "label": r["label"],
                "title": r["title"],
                "entries": len(entries),
                "chunk": chunk.chunk_id,
            }
        )
    return found
