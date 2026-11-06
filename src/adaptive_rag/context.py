"""Shared services, passed explicitly so tests can swap in fakes."""

import threading
from dataclasses import dataclass, field
from typing import Any

from adaptive_rag.config import Settings
from adaptive_rag.db import connect
from adaptive_rag.providers import EmbeddingProvider, LLMProvider
from adaptive_rag.vectorstore import VectorStore


@dataclass
class AppContext:
    settings: Settings
    embedder: EmbeddingProvider
    llm: LLMProvider
    store: VectorStore
    # One ingestion at a time keeps memory use predictable on 16 GB.
    ingest_lock: threading.Lock = field(default_factory=threading.Lock)
    # Tests swap in a mock HTTP transport for the cloud adapters. None means the real network.
    cloud_transport: Any = None

    def db(self):
        return connect(self.settings.db_path)
