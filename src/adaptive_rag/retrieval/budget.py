"""Token budgeting. Whole chunks are dropped rather than cut mid-sentence."""

from .types import RetrievedChunk


def fit_to_budget(chunks: list[RetrievedChunk], max_tokens: int) -> list[RetrievedChunk]:
    """Keep chunks in order while they fit. Later, smaller chunks may still fit."""
    selected: list[RetrievedChunk] = []
    used = 0
    for chunk in chunks:
        # evidence_tokens includes any table header context, so context is never free.
        if used + chunk.evidence_tokens <= max_tokens:
            selected.append(chunk)
            used += chunk.evidence_tokens
    return selected
