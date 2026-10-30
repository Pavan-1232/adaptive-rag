"""Chunking strategies. Stage 4 adds recursive, structure-aware, and semantic candidates."""

from .base import MAX_CHUNK_TOKENS, Chunk, count_tokens
from .fixed import STRATEGY as FIXED_STRATEGY
from .fixed import VERSION as FIXED_VERSION
from .fixed import chunk_fixed

__all__ = [
    "FIXED_STRATEGY",
    "FIXED_VERSION",
    "MAX_CHUNK_TOKENS",
    "Chunk",
    "chunk_fixed",
    "count_tokens",
]
