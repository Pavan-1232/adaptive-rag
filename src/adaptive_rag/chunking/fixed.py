"""Fixed-size token windows. This is the baseline strategy and the optimizer's control."""

from adaptive_rag.loaders import ExtractedDocument

from .base import MAX_CHUNK_TOKENS, Chunk, _encoding, locate, section_at

STRATEGY = "fixed"
VERSION = "fixed-1"


def chunk_fixed(doc: ExtractedDocument, size: int = 512, overlap: int = 50) -> list[Chunk]:
    if not 0 < size <= MAX_CHUNK_TOKENS:
        raise ValueError(f"size must be between 1 and {MAX_CHUNK_TOKENS}")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and smaller than size")

    tokens = _encoding.encode_ordinary(doc.text)
    if not tokens:
        return []
    _, offsets = _encoding.decode_with_offsets(tokens)

    chunks: list[Chunk] = []
    step = size - overlap
    for first in range(0, len(tokens), step):
        last = min(first + size, len(tokens))
        start = offsets[first]
        end = offsets[last] if last < len(tokens) else len(doc.text)
        text = doc.text[start:end]
        if text.strip():
            locator_start, locator_end = locate(doc, start, end)
            chunks.append(
                Chunk(
                    index=len(chunks),
                    start=start,
                    end=end,
                    text=text,
                    token_count=last - first,
                    locator_start=locator_start,
                    locator_end=locator_end,
                    section_heading=section_at(doc, start),
                )
            )
        if last == len(tokens):
            break
    return chunks
