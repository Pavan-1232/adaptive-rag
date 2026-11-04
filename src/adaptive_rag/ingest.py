"""The ingestion pipeline: register upload, extract, chunk, embed, store, mark ready."""

import hashlib
import json
import logging
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path

from adaptive_rag.chunking import (
    FIXED_STRATEGY,
    FIXED_VERSION,
    chunk_fixed,
    context_text,
    embedding_text,
)
from adaptive_rag.context import AppContext
from adaptive_rag.knowledge_bases import check_embedding_lock
from adaptive_rag.loaders import LOADERS, ExtractionError, validate_upload
from adaptive_rag.optimizer.candidates import BY_ID, build_chunks
from adaptive_rag.optimizer.choose import choose_chunking
from adaptive_rag.providers import EmbeddingInputTooLong, ProviderUnavailable

logger = logging.getLogger(__name__)


class VersionInProgress(Exception):
    """An earlier version of this filename is still being indexed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _stored_path(ctx: AppContext, sha256: str, file_format: str) -> Path:
    # Named by hash, so a user-supplied filename never reaches the filesystem.
    return ctx.settings.files_dir / f"{sha256}.{file_format}"


def _new_job(conn: sqlite3.Connection, document_id: int) -> int:
    return conn.execute(
        "INSERT INTO jobs (document_id, kind, status) VALUES (?, 'ingest', 'queued')",
        (document_id,),
    ).lastrowid


def register_upload(
    ctx: AppContext, kb: sqlite3.Row, temp_path: Path, filename: str
) -> tuple[sqlite3.Row, int | None, bool]:
    """Validate and store an upload. Return (document, job_id, is_duplicate)."""
    file_format = validate_upload(temp_path, filename, ctx.settings.max_upload_bytes)
    filename = Path(filename).name
    sha256 = _sha256(temp_path)
    size = temp_path.stat().st_size

    with ctx.db() as conn:
        existing = conn.execute(
            "SELECT * FROM documents WHERE kb_id = ? AND sha256 = ?", (kb["id"], sha256)
        ).fetchone()
        if existing and existing["status"] != "failed":
            return existing, None, True

        destination = _stored_path(ctx, sha256, file_format)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(temp_path, destination)

        if existing:  # A previous attempt failed, so try the same row again.
            document_id = existing["id"]
            conn.execute(
                "UPDATE documents SET status = 'pending', error = NULL, filename = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (filename, document_id),
            )
        else:
            document_id = _insert_version(conn, kb["id"], filename, file_format, sha256, size)
        job_id = _new_job(conn, document_id)
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return document, job_id, False


def _insert_version(
    conn: sqlite3.Connection, kb_id: int, filename: str, file_format: str, sha256: str, size: int
) -> int:
    earlier = conn.execute(
        "SELECT id, version, status FROM documents WHERE kb_id = ? AND filename = ?"
        " ORDER BY version DESC",
        (kb_id, filename),
    ).fetchall()
    if any(row["status"] in ("pending", "indexing") for row in earlier):
        raise VersionInProgress(filename)
    replaces = next((row["id"] for row in earlier if row["status"] == "ready"), None)
    version = earlier[0]["version"] + 1 if earlier else 1
    return conn.execute(
        "INSERT INTO documents (kb_id, filename, format, sha256, size_bytes, version,"
        " replaces_document_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (kb_id, filename, file_format, sha256, size, version, replaces),
    ).lastrowid


def _config_id(
    conn: sqlite3.Connection, strategy: str, size: int, overlap: int, version: str
) -> int:
    values = (strategy, size, overlap, version)
    conn.execute(
        "INSERT OR IGNORE INTO chunking_configs (strategy, size_tokens, overlap_tokens,"
        " chunker_version) VALUES (?, ?, ?, ?)",
        values,
    )
    return conn.execute(
        "SELECT id FROM chunking_configs WHERE strategy = ? AND size_tokens = ?"
        " AND overlap_tokens = ? AND chunker_version = ?",
        values,
    ).fetchone()["id"]


def _set_job(conn: sqlite3.Connection, job_id: int, status: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, error = ?, updated_at = datetime('now') WHERE id = ?",
        (status, error, job_id),
    )


def _fail(ctx: AppContext, job_id: int, document_id: int, message: str) -> None:
    with ctx.db() as conn:
        conn.execute(
            "UPDATE documents SET status = 'failed', error = ?, updated_at = datetime('now')"
            " WHERE id = ?",
            (message, document_id),
        )
        _set_job(conn, job_id, "failed", message)


def run_ingest_job(ctx: AppContext, job_id: int) -> None:
    """Run one job to completion. Failures are recorded on the document, never raised."""
    with ctx.ingest_lock:
        with ctx.db() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            document_id = job["document_id"]
            _set_job(conn, job_id, "running")
        try:
            _ingest(ctx, document_id)
            with ctx.db() as conn:
                _set_job(conn, job_id, "succeeded")
        except ExtractionError as exc:
            _fail(ctx, job_id, document_id, str(exc))
        except ProviderUnavailable as exc:
            _fail(ctx, job_id, document_id, str(exc))
        except EmbeddingInputTooLong:
            _fail(ctx, job_id, document_id, "A chunk exceeded the embedding model's limit.")
        except Exception:
            logger.exception("Ingest job %s failed", job_id)
            _fail(ctx, job_id, document_id, "Indexing failed because of an internal error.")
        finally:
            _unload_llm(ctx)


def _unload_llm(ctx: AppContext) -> None:
    """Release memory after ingestion. Failing to unload should not fail the job."""
    try:
        ctx.llm.unload()
    except ProviderUnavailable:
        logger.warning("Could not unload the LLM after ingestion")


def _ingest(ctx: AppContext, document_id: int) -> None:
    with ctx.db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        kb = conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (doc["kb_id"],)).fetchone()
        conn.execute(
            "UPDATE documents SET status = 'indexing', updated_at = datetime('now') WHERE id = ?",
            (document_id,),
        )
    check_embedding_lock(ctx, kb)
    collection = kb["collection_name"]

    loader = LOADERS[doc["format"]]
    extracted = loader.extract(_stored_path(ctx, doc["sha256"], doc["format"]))
    title = Path(doc["filename"]).stem
    choice = choose_chunking(ctx, extracted, doc["filename"], doc["format"], loader.version)
    if choice.candidate_id is None:
        size, overlap = ctx.settings.chunk_size_tokens, ctx.settings.chunk_overlap_tokens
        config = (FIXED_STRATEGY, size, overlap, FIXED_VERSION)
        chunks = chunk_fixed(extracted, size=size, overlap=overlap)
    else:
        candidate = BY_ID[choice.candidate_id]
        config = (candidate.strategy, candidate.size, candidate.overlap, candidate.version)
        chunks = build_chunks(candidate, extracted, ctx.embedder, title)
    if not chunks:
        raise ExtractionError("No text could be chunked from this document.")

    # Clear anything an interrupted attempt left behind.
    ctx.store.delete_document(collection, document_id)
    with ctx.db() as conn:
        config_id = _config_id(conn, *config)
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.execute(
            "UPDATE documents SET canonical_text = ?, locator_kind = ?, units = ?, sections = ?,"
            " warnings = ?, extractor_version = ?, chunking_config_id = ? WHERE id = ?",
            (
                extracted.text,
                extracted.locator_kind,
                json.dumps([asdict(unit) for unit in extracted.units]),
                json.dumps([asdict(section) for section in extracted.sections]),
                json.dumps(extracted.warnings),
                loader.version,
                config_id,
                document_id,
            ),
        )
        ids = [f"{document_id}-{chunk.index}" for chunk in chunks]
        conn.executemany(
            "INSERT INTO chunks (id, document_id, chunk_index, start_char, end_char, text,"
            " token_count, locator_start, locator_end, section_heading, chunking_config_id,"
            " context_start, context_end, context_text, context_tokens, is_table)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    chunk_id,
                    document_id,
                    chunk.index,
                    chunk.start,
                    chunk.end,
                    chunk.text,
                    chunk.token_count,
                    chunk.locator_start,
                    chunk.locator_end,
                    chunk.section_heading,
                    config_id,
                    chunk.context_start,
                    chunk.context_end,
                    context_text(extracted.text, chunk),
                    chunk.context_tokens,
                    int(chunk.is_table),
                )
                for chunk_id, chunk in zip(ids, chunks, strict=True)
            ],
        )
        conn.execute(
            "INSERT INTO optimization_runs (document_id, registry_id, action, candidate_id,"
            " detail, seconds) VALUES (?, ?, ?, ?, ?, ?)",
            (
                document_id,
                choice.registry_id,
                choice.action,
                choice.candidate_id or "fixed",
                choice.detail_json(),
                round(choice.seconds, 2),
            ),
        )

    texts = [embedding_text(extracted.text, chunk) for chunk in chunks]
    vectors = ctx.embedder.embed_documents(texts, [title] * len(chunks))
    metadatas = [
        {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk.index,
            "locator_start": chunk.locator_start,
            "locator_end": chunk.locator_end,
            "config_id": config_id,
        }
        for chunk_id, chunk in zip(ids, chunks, strict=True)
    ]
    ctx.store.add(collection, ids, vectors, metadatas)

    # Swap versions in one transaction, so a search never sees both or neither.
    with ctx.db() as conn:
        conn.execute(
            "UPDATE documents SET status = 'ready', error = NULL, updated_at = datetime('now')"
            " WHERE id = ?",
            (document_id,),
        )
        if doc["replaces_document_id"]:
            conn.execute(
                "UPDATE documents SET status = 'superseded' WHERE id = ? AND status = 'ready'",
                (doc["replaces_document_id"],),
            )
    if doc["replaces_document_id"]:
        _remove_superseded(ctx, doc["replaces_document_id"])


def _remove_superseded(ctx: AppContext, document_id: int) -> None:
    with ctx.db() as conn:
        row = conn.execute("SELECT status FROM documents WHERE id = ?", (document_id,)).fetchone()
    if row and row["status"] == "superseded":
        delete_document(ctx, document_id)


def delete_document(ctx: AppContext, document_id: int) -> None:
    """Remove vectors first. If this stops midway, the startup check finishes it."""
    with ctx.db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        kb = conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (doc["kb_id"],)).fetchone()
        conn.execute("UPDATE documents SET status = 'superseded' WHERE id = ?", (document_id,))
    ctx.store.delete_document(kb["collection_name"], document_id)
    with ctx.db() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        still_used = conn.execute(
            "SELECT 1 FROM documents WHERE sha256 = ? LIMIT 1", (doc["sha256"],)
        ).fetchone()
    if not still_used:
        _stored_path(ctx, doc["sha256"], doc["format"]).unlink(missing_ok=True)


def repair_on_startup(ctx: AppContext) -> list[int]:
    """Make SQLite and Chroma agree after a crash. Return the job IDs to re-run."""
    job_ids: list[int] = []
    with ctx.db() as conn:
        superseded = conn.execute("SELECT id FROM documents WHERE status = 'superseded'").fetchall()
    for row in superseded:
        delete_document(ctx, row["id"])

    with ctx.db() as conn:
        interrupted = conn.execute(
            "SELECT id FROM documents WHERE status IN ('pending', 'indexing')"
        ).fetchall()
        conn.execute(
            "UPDATE jobs SET status = 'failed', error = 'Interrupted by a restart.',"
            " updated_at = datetime('now') WHERE status IN ('queued', 'running')"
        )
        job_ids += [_new_job(conn, row["id"]) for row in interrupted]
        kbs = conn.execute("SELECT id, collection_name FROM knowledge_bases").fetchall()

    for kb in kbs:
        counts = ctx.store.document_counts(kb["collection_name"])
        with ctx.db() as conn:
            ready = conn.execute(
                "SELECT d.id, COUNT(c.id) AS chunk_count FROM documents d"
                " LEFT JOIN chunks c ON c.document_id = d.id"
                " WHERE d.kb_id = ? AND d.status = 'ready' GROUP BY d.id",
                (kb["id"],),
            ).fetchall()
            expected = {row["id"]: row["chunk_count"] for row in ready}
            for document_id, chunk_count in expected.items():
                if counts.get(document_id, 0) != chunk_count:
                    conn.execute(
                        "UPDATE documents SET status = 'pending' WHERE id = ?", (document_id,)
                    )
                    job_ids.append(_new_job(conn, document_id))
            active = conn.execute(
                "SELECT id FROM documents WHERE kb_id = ? AND status IN"
                " ('ready', 'pending', 'indexing')",
                (kb["id"],),
            ).fetchall()
        known = {row["id"] for row in active}
        for document_id in counts.keys() - known:
            ctx.store.delete_document(kb["collection_name"], document_id)
    return job_ids
