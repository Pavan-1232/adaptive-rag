"""In-memory retrieval scoring with NumPy, so testing a candidate never touches Chroma.

The setup mirrors the Stage 3 runner: exact cosine search, a pool of 30, Recall@budget at 2560
tokens, hit and recall at 5, and MRR. Every chunk is charged its evidence tokens (text plus any
table header context), the same cost the LLM evidence budget uses.
"""

from dataclasses import dataclass, field

import numpy as np

from adaptive_rag.chunking import Chunk, embedding_text
from adaptive_rag.evaluation.benchmark import BenchmarkQuestion
from adaptive_rag.evaluation.metrics import (
    RankedChunk,
    Span,
    hit_at_k,
    recall_at_budget,
    recall_at_k,
    reciprocal_rank,
)
from adaptive_rag.evaluation.spans import locate_quote, page_range
from adaptive_rag.loaders import ExtractedDocument

POOL_SIZE = 30
RECALL_BUDGET_TOKENS = 2560
METRIC_K = 5


@dataclass
class DocumentChunks:
    name: str
    doc: ExtractedDocument
    chunks: list[Chunk]
    title: str = "none"


@dataclass
class QuestionScore:
    id: str
    recall_at_budget: float
    recall_at_5: float
    hit_at_5: float
    reciprocal_rank: float
    gold_rank: int | None  # rank of the first hit in the pool, if any


@dataclass
class InMemoryIndex:
    """One vector per chunk, across one or more documents (like one knowledge base)."""

    parts: list[DocumentChunks]
    embedder: object
    vectors: np.ndarray = field(init=False)
    ranked: list[RankedChunk] = field(init=False)

    def __post_init__(self) -> None:
        texts, titles, ranked = [], [], []
        for part in self.parts:
            for chunk in part.chunks:
                texts.append(embedding_text(part.doc.text, chunk))
                titles.append(part.title)
                ranked.append(RankedChunk(part.name, chunk.start, chunk.end, chunk.evidence_tokens))
        vectors = np.asarray(self.embedder.embed_documents(texts, titles), dtype=np.float32)
        norms = np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        self.vectors = vectors / norms
        self.ranked = ranked

    def search(self, query_vector: list[float], k: int = POOL_SIZE) -> list[RankedChunk]:
        query = np.asarray(query_vector, dtype=np.float32)
        query /= max(float(np.linalg.norm(query)), 1e-12)
        scores = self.vectors @ query
        order = np.argsort(-scores, kind="stable")[:k]
        return [self.ranked[i] for i in order]

    @property
    def storage_tokens(self) -> int:
        return sum(chunk.token_count for chunk in self.ranked)


def question_spans(question: BenchmarkQuestion, doc: ExtractedDocument) -> list[Span]:
    spans = []
    for item in question.evidence:
        found = [
            locate_quote(doc.text, option.quote, page_range(doc.units, option.page))
            for option in (item, *item.alternatives)
        ]
        if None in found:
            raise ValueError(f"{question.id}: evidence quote not found in {question.document}")
        alternatives = tuple(Span(question.document, *where) for where in found[1:])
        spans.append(Span(question.document, *found[0], alternatives))
    return spans


def score_question(
    index: InMemoryIndex, query_vector: list[float], question_id: str, spans: list[Span]
) -> QuestionScore:
    pool = index.search(query_vector)
    rr = reciprocal_rank(pool, spans)
    return QuestionScore(
        id=question_id,
        recall_at_budget=recall_at_budget(pool, spans, RECALL_BUDGET_TOKENS),
        recall_at_5=recall_at_k(pool, spans, METRIC_K),
        hit_at_5=hit_at_k(pool, spans, METRIC_K),
        reciprocal_rank=rr,
        gold_rank=round(1 / rr) if rr else None,
    )
