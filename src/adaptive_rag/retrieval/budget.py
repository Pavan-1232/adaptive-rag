"""Token budgeting. Whole chunks are dropped rather than cut mid-sentence."""

from .types import RetrievedChunk


def fit_to_budget(chunks: list[RetrievedChunk], max_tokens: int) -> list[RetrievedChunk]:
    """Keep chunks in order while they fit. Later, smaller chunks may still fit."""
    selected: list[RetrievedChunk] = []
    used = 0
    for chunk in chunks:
        if used + chunk.token_count <= max_tokens:
            selected.append(chunk)
            used += chunk.token_count
    return selected
