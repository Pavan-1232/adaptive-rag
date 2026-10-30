"""A thin wrapper over ChromaDB. Vectors are always computed outside and passed in."""

import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    document_id: int
    score: float


def collection_name(kb_id: int, model: str, version: str) -> str:
    """One collection per knowledge base and embedding model, so re-indexing can run alongside."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", model.split(":")[0]).strip("_")
    return f"kb_{kb_id}__{slug}_{version[:8]}"


class VectorStore:
    def __init__(self, path: Path):
        self._client = chromadb.PersistentClient(
            path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
        )

    def _collection(self, name: str):
        # The distance metric can't be changed after creation.
        return self._client.get_or_create_collection(
            name=name, configuration={"hnsw": {"space": "cosine"}}
        )

    def add(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        target = self._collection(collection)
        batch = self._client.get_max_batch_size()
        for start in range(0, len(ids), batch):
            end = start + batch
            target.upsert(
                ids=ids[start:end], embeddings=embeddings[start:end], metadatas=metadatas[start:end]
            )

    def query(
        self, collection: str, embedding: list[float], n: int, document_ids: list[int]
    ) -> list[VectorHit]:
        """Search only the given documents. Scores are cosine similarity, higher is better."""
        if not document_ids:
            return []
        result = self._collection(collection).query(
            query_embeddings=[embedding],
            n_results=n,
            where={"document_id": {"$in": document_ids}},
            include=["distances", "metadatas"],
        )
        return [
            VectorHit(chunk_id, int(metadata["document_id"]), 1.0 - distance)
            for chunk_id, metadata, distance in zip(
                result["ids"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]

    def delete_document(self, collection: str, document_id: int) -> None:
        self._collection(collection).delete(where={"document_id": document_id})

    def document_counts(self, collection: str) -> dict[int, int]:
        """Vectors per document, for the startup consistency check."""
        metadatas = self._collection(collection).get(include=["metadatas"])["metadatas"]
        counts: dict[int, int] = {}
        for metadata in metadatas:
            document_id = int(metadata["document_id"])
            counts[document_id] = counts.get(document_id, 0) + 1
        return counts
