"""The chunking candidates (DESIGN.md section 5), in simplicity order for tie-breaking."""

from collections.abc import Callable
from dataclasses import dataclass

from adaptive_rag.chunking import (
    FIXED_VERSION,
    RECURSIVE_VERSION,
    TABLE_AWARE_VERSION,
    Chunk,
    chunk_fixed,
    chunk_recursive,
    chunk_table_aware,
)
from adaptive_rag.chunking.semantic import VERSION as SEMANTIC_VERSION
from adaptive_rag.chunking.semantic import chunk_semantic
from adaptive_rag.chunking.structure import VERSION as STRUCTURE_VERSION
from adaptive_rag.chunking.structure import chunk_structure
from adaptive_rag.loaders import ExtractedDocument

from .profile import Profile

# Ties go to the simplest: fixed, recursive, structure-aware, table-aware, semantic.
SIMPLICITY = {"fixed": 0, "recursive": 1, "structure": 2, "table_aware": 3, "semantic": 4}


@dataclass(frozen=True)
class Candidate:
    id: str
    strategy: str
    size: int
    overlap: int
    version: str
    needs_embedder: bool = False

    def applies(self, profile: Profile) -> bool:
        if self.strategy == "structure":
            return profile.headings_reliable
        if self.strategy == "table_aware":
            return profile.has_tables
        return True

    @property
    def simplicity(self) -> int:
        return SIMPLICITY[self.strategy]


CANDIDATES = (
    Candidate("C1", "fixed", 512, 50, FIXED_VERSION),
    Candidate("C2", "recursive", 256, 25, RECURSIVE_VERSION),
    Candidate("C3", "recursive", 512, 50, RECURSIVE_VERSION),
    Candidate("C4", "recursive", 1024, 100, RECURSIVE_VERSION),
    Candidate("C5", "structure", 512, 50, STRUCTURE_VERSION),
    Candidate("C6", "semantic", 512, 0, SEMANTIC_VERSION, needs_embedder=True),
    Candidate("C7", "table_aware", 512, 50, TABLE_AWARE_VERSION),
)
BY_ID = {c.id: c for c in CANDIDATES}

_CHUNKERS: dict[str, Callable[..., list[Chunk]]] = {
    "fixed": chunk_fixed,
    "recursive": chunk_recursive,
    "structure": chunk_structure,
    "table_aware": chunk_table_aware,
}


def build_chunks(
    candidate: Candidate,
    doc: ExtractedDocument,
    embedder=None,
    title: str = "none",
    regions: list[tuple[int, int]] | None = None,
) -> list[Chunk]:
    """Chunk with one candidate. Semantic chunking can be limited to sampled regions."""
    if candidate.strategy == "semantic":
        if embedder is None:
            raise ValueError("semantic chunking needs an embedder")
        return chunk_semantic(doc, embedder, candidate.size, title, regions)
    return _CHUNKERS[candidate.strategy](doc, candidate.size, candidate.overlap)
