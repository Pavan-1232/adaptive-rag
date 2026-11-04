"""Recursive splitting on character offsets: paragraphs, then lines, sentences, words, tokens.

Pieces are split at the most natural separator that makes them fit, then merged greedily up to
the size limit. Overlap repeats at most `overlap` trailing tokens of the previous chunk, starting
at a sentence boundary where possible and never mid-word.
"""

import re

from adaptive_rag.loaders import ExtractedDocument

from .base import MAX_CHUNK_TOKENS, Chunk, _encoding, count_tokens, make_chunk

STRATEGY = "recursive"
VERSION = "recursive-1"

# Each pattern matches the separator; the separator stays with the piece before it.
SEPARATORS = (
    re.compile(r"\n\s*\n"),
    re.compile(r"\n"),
    re.compile(r"(?<=[.!?])\s+"),
    re.compile(r" +"),
)


def check_settings(size: int, overlap: int) -> None:
    if not 0 < size <= MAX_CHUNK_TOKENS:
        raise ValueError(f"size must be between 1 and {MAX_CHUNK_TOKENS}")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and smaller than size")


def _token_split(text: str, start: int, end: int, size: int) -> list[tuple[int, int]]:
    tokens = _encoding.encode_ordinary(text[start:end])
    _, offsets = _encoding.decode_with_offsets(tokens)
    pieces = []
    for first in range(0, len(tokens), size):
        last = first + size
        stop = start + offsets[last] if last < len(tokens) else end
        pieces.append((start + offsets[first], stop))
    return pieces


def _pieces(text: str, start: int, end: int, size: int, level: int = 0) -> list[tuple[int, int]]:
    """Split [start, end) into ranges of at most `size` tokens, at the coarsest separator."""
    if count_tokens(text[start:end]) <= size:
        return [(start, end)]
    if level == len(SEPARATORS):
        return _token_split(text, start, end, size)
    cuts = [m.end() for m in SEPARATORS[level].finditer(text, start, end) if start < m.end() < end]
    if not cuts:
        return _pieces(text, start, end, size, level + 1)
    result = []
    for left, right in zip([start, *cuts], [*cuts, end], strict=True):
        result += _pieces(text, left, right, size, level + 1)
    return result


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


_SENTENCE_GAP = re.compile(r"[.!?]\s+")


def _overlap_start(text: str, start: int, end: int, overlap: int) -> int | None:
    """Where the next chunk's overlap begins: the last `overlap` tokens of [start, end),
    moved forward to a sentence boundary if there is one, else to a word boundary."""
    tokens = _encoding.encode_ordinary(text[start:end])
    if len(tokens) <= overlap:
        return None  # the whole chunk would repeat
    _, offsets = _encoding.decode_with_offsets(tokens)
    position = start + offsets[len(tokens) - overlap]
    sentence = _SENTENCE_GAP.search(text, position, end)
    if sentence and sentence.end() < end:
        position = sentence.end()
    elif position > start and not text[position - 1].isspace():
        space = text.find(" ", position, end)
        position = end if space < 0 else space + 1
    return position if position < end else None


def split_ranges(text: str, start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    """Chunk ranges for one stretch of text, trimmed of surrounding whitespace."""
    pieces = [p for p in _pieces(text, start, end, size) if text[p[0] : p[1]].strip()]
    ranges: list[tuple[int, int]] = []
    carried: int | None = None  # overlap start carried from the previous chunk
    i = 0
    while i < len(pieces):
        first = pieces[i][0] if carried is None else carried
        if count_tokens(text[first : pieces[i][1]]) > size:
            first = pieces[i][0]  # the overlap would push the chunk over size
        last = i
        while last + 1 < len(pieces) and count_tokens(text[first : pieces[last + 1][1]]) <= size:
            last += 1
        chunk = _trim(text, first, pieces[last][1])
        ranges.append(chunk)
        i = last + 1
        carried = _overlap_start(text, *chunk, overlap) if overlap else None
    return ranges


def chunk_recursive(doc: ExtractedDocument, size: int = 512, overlap: int = 50) -> list[Chunk]:
    check_settings(size, overlap)
    ranges = split_ranges(doc.text, 0, len(doc.text), size, overlap)
    return [make_chunk(doc, index, start, end) for index, (start, end) in enumerate(ranges)]
