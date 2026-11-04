"""A disk cache for document embeddings, so re-scoring a candidate never re-embeds the same text.

The key covers everything that changes a vector: model, model digest, prompt version, title, and
text. Vectors are float32. The cache lives under data/ and is gitignored.
"""

import hashlib
import sqlite3
from pathlib import Path

import numpy as np

from adaptive_rag.providers import EmbeddingProvider


class CachedEmbeddings:
    def __init__(self, embedder: EmbeddingProvider, path: Path):
        self.inner = embedder
        self.model = embedder.model
        self.prompt_version = embedder.prompt_version
        self.id = embedder.id
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, v BLOB)")
        self._digest = embedder.version()
        self.hits = self.misses = 0

    def version(self) -> str:
        return self._digest

    def dimensions(self) -> int:
        return self.inner.dimensions()

    def _key(self, text: str, title: str) -> str:
        raw = "\x1f".join([self.model, self._digest, self.prompt_version, title, text])
        return hashlib.sha256(raw.encode()).hexdigest()

    def embed_documents(self, texts: list[str], titles: list[str]) -> list[list[float]]:
        keys = [self._key(t, title) for t, title in zip(texts, titles, strict=True)]
        found: dict[str, list[float]] = {}
        for start in range(0, len(keys), 500):
            batch = keys[start : start + 500]
            rows = self._conn.execute(
                f"SELECT key, v FROM vectors WHERE key IN ({','.join('?' * len(batch))})",  # noqa: S608
                batch,
            ).fetchall()
            found.update({k: np.frombuffer(v, dtype=np.float32).tolist() for k, v in rows})
        missing = [i for i, k in enumerate(keys) if k not in found]
        self.hits += len(keys) - len(missing)
        self.misses += len(missing)
        if missing:
            vectors = self.inner.embed_documents(
                [texts[i] for i in missing], [titles[i] for i in missing]
            )
            with self._conn:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO vectors VALUES (?, ?)",
                    [
                        (keys[i], np.asarray(v, dtype=np.float32).tobytes())
                        for i, v in zip(missing, vectors, strict=True)
                    ],
                )
            for i, v in zip(missing, vectors, strict=True):
                found[keys[i]] = list(v)
        return [found[k] for k in keys]

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text)
