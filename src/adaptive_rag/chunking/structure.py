"""C5: structure-aware chunking. Chunks never cross a section boundary.

Each section (heading to next heading) is split recursively on its own. Very short sections,
usually a heading with one line under it or a false heading, are merged into the next section
so they don't become tiny chunks. Only used when the profiler finds the headings reliable.
"""

from adaptive_rag.loaders import ExtractedDocument

from .base import Chunk, count_tokens, make_chunk
from .recursive import check_settings, split_ranges

STRATEGY = "structure"
VERSION = "structure-1"

MIN_SECTION_TOKENS = 50


def section_groups(doc: ExtractedDocument) -> list[tuple[int, int]]:
    """Character ranges to chunk independently: the text before the first heading, then each
    section, with sections under MIN_SECTION_TOKENS merged forward."""
    bounds = sorted({0, len(doc.text), *(s.start for s in doc.sections if 0 < s.start)})
    groups: list[tuple[int, int]] = []
    start = 0
    for end in bounds[1:]:
        if count_tokens(doc.text[start:end]) < MIN_SECTION_TOKENS and end < len(doc.text):
            continue  # too short: keep extending into the next section
        groups.append((start, end))
        start = end
    if start < len(doc.text):
        if groups:
            groups[-1] = (groups[-1][0], len(doc.text))
        else:
            groups.append((start, len(doc.text)))
    return groups


def chunk_structure(doc: ExtractedDocument, size: int = 512, overlap: int = 50) -> list[Chunk]:
    check_settings(size, overlap)
    chunks: list[Chunk] = []
    for group_start, group_end in section_groups(doc):
        for start, end in split_ranges(doc.text, group_start, group_end, size, overlap):
            chunks.append(make_chunk(doc, len(chunks), start, end))
    return chunks
