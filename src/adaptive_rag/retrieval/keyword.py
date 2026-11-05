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


def match_query(text: str) -> str | None:
    words = [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None


def keyword_search(
    ctx: AppContext, text: str, n: int, document_ids: list[int]
) -> list[tuple[str, float]]:
    """(chunk_id, strength) best first, strength = BM25 relative to the best hit, in 0..1."""
    query = match_query(text)
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
