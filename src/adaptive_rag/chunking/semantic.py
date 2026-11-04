"""C6: semantic chunking. Cut where the topic shifts, measured by embedding distance.

Each sentence is embedded together with its neighbours (one each side). A cut goes where the
distance between consecutive sentence windows is in the top (100 - percentile)%. Groups over the
size limit are split recursively; groups under MIN_TOKENS join the next one if they fit.

This is the costliest candidate: it embeds about three times the text it chunks. The design
tests it rather than assuming it helps (see DESIGN.md section 5).
"""

import re

import numpy as np

from adaptive_rag.loaders import ExtractedDocument
from adaptive_rag.providers import EmbeddingProvider

from .base import Chunk, count_tokens, make_chunk
from .recursive import check_settings, split_ranges

STRATEGY = "semantic"
VERSION = "semantic-1"

PERCENTILE = 95
BUFFER = 1
MIN_TOKENS = 64
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n\s*\n")


def sentence_ranges(text: str, start: int, end: int, size: int) -> list[tuple[int, int]]:
    """Sentences in [start, end), trimmed; a sentence over `size` tokens is split further."""
    cuts = [m.end() for m in _SENTENCE_END.finditer(text, start, end)]
    ranges = []
    for left, right in zip([start, *cuts], [*cuts, end], strict=True):
        for piece in split_ranges(text, left, right, size, 0):
            if piece[1] > piece[0]:
                ranges.append(piece)
    return ranges


def breakpoints(vectors: np.ndarray, percentile: float = PERCENTILE) -> list[int]:
    """Indexes i where a cut goes between sentence i and i + 1."""
    if len(vectors) < 2:
        return []
    unit = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    distances = 1.0 - np.sum(unit[:-1] * unit[1:], axis=1)
    threshold = np.percentile(distances, percentile)
    return [i for i, distance in enumerate(distances) if distance > threshold]


def chunk_semantic(
    doc: ExtractedDocument,
    embedder: EmbeddingProvider,
    size: int = 512,
    title: str = "none",
    regions: list[tuple[int, int]] | None = None,
) -> list[Chunk]:
    """Chunk the whole document, or only `regions` (the optimizer's sample) to save cost."""
    check_settings(size, 0)
    text = doc.text
    chunks: list[Chunk] = []
    for region_start, region_end in regions or [(0, len(text))]:
        sentences = sentence_ranges(text, region_start, region_end, size)
        if not sentences:
            continue
        windows = [
            text[
                sentences[max(i - BUFFER, 0)][0] : sentences[min(i + BUFFER, len(sentences) - 1)][1]
            ]
            for i in range(len(sentences))
        ]
        # A window of three sentences can pass the embedding limit; fall back to the sentence.
        windows = [
            w if count_tokens(w) <= 2 * size else text[slice(*s)]
            for w, s in zip(windows, sentences, strict=True)
        ]
        vectors = np.asarray(embedder.embed_documents(windows, [title] * len(windows)))
        cuts = set(breakpoints(vectors))
        groups, first = [], 0
        for i in range(len(sentences)):
            if i in cuts or i == len(sentences) - 1:
                groups.append((sentences[first][0], sentences[i][1]))
                first = i + 1
        for start, end in _merge_small(text, groups, size):
            for left, right in split_ranges(text, start, end, size, 0):
                chunks.append(make_chunk(doc, len(chunks), left, right))
    return chunks


def _merge_small(text: str, groups: list[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in groups:
        if merged and count_tokens(text[merged[-1][0] : merged[-1][1]]) < MIN_TOKENS:
            if count_tokens(text[merged[-1][0] : end]) <= size:
                merged[-1] = (merged[-1][0], end)
                continue
        merged.append((start, end))
    return merged
