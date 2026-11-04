"""Fixed top-k vector search: the reference that adaptive retrieval must beat."""

import sqlite3

from adaptive_rag.context import AppContext
from adaptive_rag.knowledge_bases import check_embedding_lock

from .types import RetrievedChunk


def retrieve_baseline(
    ctx: AppContext, kb: sqlite3.Row, question: str, k: int
) -> list[RetrievedChunk]:
    check_embedding_lock(ctx, kb)
    with ctx.db() as conn:
        rows = conn.execute(
            "SELECT id FROM documents WHERE kb_id = ? AND status = 'ready'", (kb["id"],)
        ).fetchall()
    document_ids = [row["id"] for row in rows]
    if not document_ids:
        return []

    embedding = ctx.embedder.embed_query(question)
    hits = ctx.store.query(kb["collection_name"], embedding, k, document_ids)
    if not hits:
        return []

    placeholders = ",".join("?" * len(hits))
    query = (
        "SELECT c.*, d.filename, d.locator_kind FROM chunks c"  # noqa: S608
        f" JOIN documents d ON d.id = c.document_id WHERE c.id IN ({placeholders})"
        " AND d.status = 'ready'"
    )
    with ctx.db() as conn:
        rows = conn.execute(query, [hit.chunk_id for hit in hits]).fetchall()
    by_id = {row["id"]: row for row in rows}
    return [
        RetrievedChunk(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            filename=by_id[hit.chunk_id]["filename"],
            chunk_index=by_id[hit.chunk_id]["chunk_index"],
            text=by_id[hit.chunk_id]["text"],
            token_count=by_id[hit.chunk_id]["token_count"],
            score=hit.score,
            locator_kind=by_id[hit.chunk_id]["locator_kind"],
            locator_start=by_id[hit.chunk_id]["locator_start"],
            locator_end=by_id[hit.chunk_id]["locator_end"],
            section_heading=by_id[hit.chunk_id]["section_heading"],
            start_char=by_id[hit.chunk_id]["start_char"],
            end_char=by_id[hit.chunk_id]["end_char"],
            context_text=by_id[hit.chunk_id]["context_text"],
            context_tokens=by_id[hit.chunk_id]["context_tokens"],
        )
        for hit in hits
        if hit.chunk_id in by_id
    ]
