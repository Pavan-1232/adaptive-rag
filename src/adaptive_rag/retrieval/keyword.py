"""Keyword search over chunk text with SQLite FTS5 (BM25), for hybrid retrieval.

Dense search ranks table rows poorly ("Lathrop", "Automotive sales"): their exact words are
the strongest signal. Questions are turned into an OR of quoted words, so user text can
never be read as FTS5 query syntax.
"""

import re

from adaptive_rag.context import AppContext

_WORD = re.compile(r"\w+")
_STOP = frozenset(
    "a an and are as at be been by did do does for from had has have how in is it its of on or"
    " that the their this to was were what when where which who why will with".split()
)


def match_query(text: str, style: str = "words") -> str | None:
    """ "words": an OR of single words, stop words and one-letter words dropped (Stage 5).
    "phrases" (2026-11-09, real use): also keeps a stop word or short token next to a number,
    so "AS 20" and "Q.5" survive, and adds adjacent kept words as quoted phrases."""
    tokens = _WORD.findall(text.lower())
    if style == "words":
        words = [w for w in tokens if w not in _STOP and len(w) > 1]
        return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None
    if style != "phrases":
        raise ValueError(f"unknown keyword query style: {style}")

    def number(i: int) -> bool:
        return 0 <= i < len(tokens) and tokens[i].isdigit()

    keep = [
        w.isdigit() or (w not in _STOP and len(w) > 1) or number(i - 1) or number(i + 1)
        for i, w in enumerate(tokens)
    ]
    pairs = [
        f'"{tokens[i]} {tokens[i + 1]}"' for i in range(len(tokens) - 1) if keep[i] and keep[i + 1]
    ]
    words = [f'"{w}"' for w, kept in zip(tokens, keep, strict=True) if kept]
    return " OR ".join(dict.fromkeys(pairs + words)) or None


def numeric_phrases(text: str) -> list[str]:
    """Adjacent word pairs of the question that contain a number ("q 5", "may 2026", "as 20")."""
    query = match_query(text, "phrases") or ""
    return [t for t in query.split(" OR ") if " " in t and any(ch.isdigit() for ch in t)]


def exact_hit(ctx: AppContext, text: str, document_ids: list[int]) -> str | None:
    """The best keyword match for the question's numeric phrases only, or None."""
    phrases = numeric_phrases(text)
    if not phrases or not document_ids:
        return None
    placeholders = ",".join("?" * len(document_ids))
    sql = (
        "SELECT f.chunk_id FROM chunks_fts f JOIN chunks c ON c.id = f.chunk_id"  # noqa: S608
        f" WHERE chunks_fts MATCH ? AND c.document_id IN ({placeholders}) ORDER BY rank LIMIT 1"
    )
    with ctx.db() as conn:
        row = conn.execute(sql, [" OR ".join(phrases), *document_ids]).fetchone()
    return row["chunk_id"] if row else None


def keyword_search(
    ctx: AppContext, text: str, n: int, document_ids: list[int], style: str = "words"
) -> list[tuple[str, float]]:
    """(chunk_id, strength) best first, strength = BM25 relative to the best hit, in 0..1."""
    query = match_query(text, style)
    if query is None or not document_ids:
        return []
    placeholders = ",".join("?" * len(document_ids))
    # Only "?" placeholders are formatted in; all values are bound.
    sql = (
        "SELECT f.chunk_id, bm25(chunks_fts) AS rank FROM chunks_fts f"  # noqa: S608
        " JOIN chunks c ON c.id = f.chunk_id"
        f" WHERE chunks_fts MATCH ? AND c.document_id IN ({placeholders})"
        " ORDER BY rank LIMIT ?"
    )
    with ctx.db() as conn:
        rows = conn.execute(sql, [query, *document_ids, n]).fetchall()
    if not rows:
        return []
    best = rows[0]["rank"]  # bm25() is negative; more negative is better
    return [(row["chunk_id"], row["rank"] / best if best else 0.0) for row in rows]
