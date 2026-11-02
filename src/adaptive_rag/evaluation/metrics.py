"""Retrieval metrics. All work on character spans, so they compare across chunking configs.

Hit rate, recall@k, and MRR favour large chunks. Recall@budget is the primary metric because
it charges each system for the tokens it retrieves.
"""

from dataclasses import dataclass

from .spans import overlap

HIT_COVERAGE = 0.5


@dataclass(frozen=True)
class Span:
    """One required fact. Covering any one of its alternatives counts as covering it."""

    document: str
    start: int
    end: int
    alternatives: tuple["Span", ...] = ()

    def options(self) -> tuple["Span", ...]:
        return (self, *self.alternatives)


@dataclass(frozen=True)
class RankedChunk:
    document: str
    start: int
    end: int
    token_count: int


def _covered_chars(chunks: list[RankedChunk], evidence: Span) -> int:
    """Characters of the evidence covered by any chunk, without counting overlaps twice."""
    ranges = sorted(
        (max(chunk.start, evidence.start), min(chunk.end, evidence.end))
        for chunk in chunks
        if chunk.document == evidence.document
        and chunk.start < evidence.end
        and chunk.end > evidence.start
    )
    covered, reach = 0, evidence.start
    for start, end in ranges:
        start = max(start, reach)
        if end > start:
            covered += end - start
            reach = end
    return covered


def _best_coverage(chunks: list[RankedChunk], span: Span) -> float:
    return (
        max(
            _covered_chars(chunks, option) / (option.end - option.start)
            for option in span.options()
            if option.end > option.start
        )
        if span.end > span.start
        else 0.0
    )


def evidence_recall(chunks: list[RankedChunk], evidence: list[Span]) -> float:
    total = sum(span.end - span.start for span in evidence)
    if total == 0:
        return 0.0
    return sum((span.end - span.start) * _best_coverage(chunks, span) for span in evidence) / total


def recall_at_k(chunks: list[RankedChunk], evidence: list[Span], k: int) -> float:
    return evidence_recall(chunks[:k], evidence)


def recall_at_budget(chunks: list[RankedChunk], evidence: list[Span], budget: int) -> float:
    """Evidence covered by whole chunks, in rank order, until the next one wouldn't fit."""
    selected: list[RankedChunk] = []
    used = 0
    for chunk in chunks:
        if used + chunk.token_count > budget:
            break
        selected.append(chunk)
        used += chunk.token_count
    return evidence_recall(selected, evidence)


def is_hit(chunk: RankedChunk, evidence: list[Span]) -> bool:
    """A chunk hits if it covers at least half of any one evidence span."""
    for required in evidence:
        for span in required.options():
            if span.document != chunk.document or span.end <= span.start:
                continue
            shared = overlap(chunk.start, chunk.end, span.start, span.end)
            if shared / (span.end - span.start) >= HIT_COVERAGE:
                return True
    return False


def hit_at_k(chunks: list[RankedChunk], evidence: list[Span], k: int) -> float:
    return float(any(is_hit(chunk, evidence) for chunk in chunks[:k]))


def reciprocal_rank(chunks: list[RankedChunk], evidence: list[Span]) -> float:
    for rank, chunk in enumerate(chunks, start=1):
        if is_hit(chunk, evidence):
            return 1 / rank
    return 0.0
