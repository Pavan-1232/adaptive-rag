"""Fixed top-k vector search: the reference that adaptive retrieval must beat."""

import sqlite3

from adaptive_rag.context import AppContext
from adaptive_rag.knowledge_bases import check_embedding_lock

from .types import RetrievedChunk


def retrieve_baseline(
    ctx: AppContext, kb: sqlite3.Row, question: str, k: int
) -> list[RetrievedChunk]:
    check_embedding_lock(ctx, kb)
    document_ids = ready_document_ids(ctx, kb)
    if not document_ids:
        return []

    embedding = ctx.embedder.embed_query(question)
    hits = ctx.store.query(kb["collection_name"], embedding, k, document_ids)
    if not hits:
        return []

    return load_chunks(ctx, [(hit.chunk_id, hit.score) for hit in hits])


def ready_document_ids(ctx: AppContext, kb: sqlite3.Row) -> list[int]:
    with ctx.db() as conn:
        rows = conn.execute(
            "SELECT id FROM documents WHERE kb_id = ? AND status = 'ready'", (kb["id"],)
        ).fetchall()
    return [row["id"] for row in rows]


def _to_chunk(row: sqlite3.Row, score: float, source: str = "direct") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row["id"],
        document_id=row["document_id"],
        filename=row["filename"],
        chunk_index=row["chunk_index"],
        text=row["text"],
        token_count=row["token_count"],
        score=score,
        locator_kind=row["locator_kind"],
        locator_start=row["locator_start"],
        locator_end=row["locator_end"],
        section_heading=row["section_heading"],
        source=source,
        start_char=row["start_char"],
        end_char=row["end_char"],
        context_text=row["context_text"],
        context_tokens=row["context_tokens"],
    )


_CHUNK_SELECT = (
    "SELECT c.*, d.filename, d.locator_kind FROM chunks c"
    " JOIN documents d ON d.id = c.document_id WHERE d.status = 'ready' AND "
)


def load_chunks(ctx: AppContext, scored: list[tuple[str, float]]) -> list[RetrievedChunk]:
    """Chunk rows for (chunk_id, score) pairs, in the given order. Missing rows are skipped."""
    if not scored:
        return []
    placeholders = ",".join("?" * len(scored))
    with ctx.db() as conn:
        rows = conn.execute(
            _CHUNK_SELECT + f"c.id IN ({placeholders})",  # noqa: S608
            [chunk_id for chunk_id, _ in scored],
        ).fetchall()
    by_id = {row["id"]: row for row in rows}
    return [_to_chunk(by_id[chunk_id], score) for chunk_id, score in scored if chunk_id in by_id]


def load_neighbor(
    ctx: AppContext, document_id: int, chunk_index: int, parent_score: float
) -> RetrievedChunk | None:
    """The chunk at chunk_index in the same document, marked as an expansion."""
    with ctx.db() as conn:
        row = conn.execute(
            _CHUNK_SELECT + "c.document_id = ? AND c.chunk_index = ?",
            (document_id, chunk_index),
        ).fetchone()
    return None if row is None else _to_chunk(row, parent_score, "expansion")
