"""Chunking strategies. Stage 4 adds recursive, structure-aware, semantic, and table-aware."""

from .base import MAX_CHUNK_TOKENS, Chunk, context_text, count_tokens, embedding_text
from .fixed import STRATEGY as FIXED_STRATEGY
from .fixed import VERSION as FIXED_VERSION
from .fixed import chunk_fixed
from .recursive import STRATEGY as RECURSIVE_STRATEGY
from .recursive import VERSION as RECURSIVE_VERSION
from .recursive import chunk_recursive
from .table_aware import STRATEGY as TABLE_AWARE_STRATEGY
from .table_aware import VERSION as TABLE_AWARE_VERSION
from .table_aware import chunk_table_aware
from .tables import find_tables

__all__ = [
    "FIXED_STRATEGY",
    "FIXED_VERSION",
    "MAX_CHUNK_TOKENS",
    "RECURSIVE_STRATEGY",
    "RECURSIVE_VERSION",
    "TABLE_AWARE_STRATEGY",
    "TABLE_AWARE_VERSION",
    "Chunk",
    "chunk_fixed",
    "chunk_recursive",
    "chunk_table_aware",
    "context_text",
    "count_tokens",
    "embedding_text",
    "find_tables",
]
