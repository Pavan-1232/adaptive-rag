"""Knowledge base creation. Each one is locked to the embedding model it was created with."""

import sqlite3

from adaptive_rag.context import AppContext
from adaptive_rag.vectorstore import collection_name


class KnowledgeBaseExists(Exception):
    pass


class EmbeddingModelMismatch(Exception):
    """The configured embedding model differs from the one this knowledge base was built with."""


def create_knowledge_base(ctx: AppContext, name: str, allow_cloud: bool = False) -> sqlite3.Row:
    version = ctx.embedder.version()
    dimensions = ctx.embedder.dimensions()
    with ctx.db() as conn:
        try:
            kb_id = conn.execute(
                "INSERT INTO knowledge_bases (name, embedding_provider, embedding_model,"
                " embedding_version, embedding_dimensions, embedding_prompt_version,"
                " collection_name, allow_cloud) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    ctx.embedder.id,
                    ctx.embedder.model,
                    version,
                    dimensions,
                    ctx.embedder.prompt_version,
                    f"pending-{name}",
                    int(allow_cloud),
                ),
            ).lastrowid
        except sqlite3.IntegrityError as exc:
            raise KnowledgeBaseExists(name) from exc
        conn.execute(
            "UPDATE knowledge_bases SET collection_name = ? WHERE id = ?",
            (collection_name(kb_id, ctx.embedder.model, version), kb_id),
        )
        return conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)).fetchone()


def check_embedding_lock(ctx: AppContext, kb: sqlite3.Row) -> None:
    """Vectors from different models can't be compared, so mixing them must fail loudly."""
    configured = (ctx.embedder.id, ctx.embedder.model, ctx.embedder.version())
    recorded = (kb["embedding_provider"], kb["embedding_model"], kb["embedding_version"])
    if configured != recorded or ctx.embedder.prompt_version != kb["embedding_prompt_version"]:
        raise EmbeddingModelMismatch(
            f"Knowledge base '{kb['name']}' was built with {kb['embedding_model']}. "
            "Using a different embedding model requires a re-index."
        )
