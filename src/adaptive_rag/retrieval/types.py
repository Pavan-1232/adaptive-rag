from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: int
    filename: str
    chunk_index: int
    text: str
    token_count: int
    score: float
    locator_kind: str
    locator_start: int
    locator_end: int
    section_heading: str | None
    source: Literal["direct", "expansion", "answer_key"] = "direct"
    start_char: int = 0
    end_char: int = 0
    # C7 table header shown before the chunk text; its tokens are charged to the budget.
    context_text: str | None = None
    context_tokens: int = 0
    # Hybrid search: BM25 strength in 0..1 (1 = best keyword hit for the query). 0 when off.
    keyword: float = 0.0
    # A merged evidence block: the chunks it was built from, in document order. Empty for a
    # plain chunk. The block's own fields span all members; score is the best direct score.
    members: tuple["RetrievedChunk", ...] = ()

    @property
    def evidence_tokens(self) -> int:
        return self.token_count + self.context_tokens

    @property
    def pieces(self) -> tuple["RetrievedChunk", ...]:
        """The stored chunks behind this evidence: its members, or itself."""
        return self.members or (self,)

    @property
    def evidence_text(self) -> str:
        """What the LLM reads: the context, then the chunk."""
        return self.text if self.context_text is None else f"{self.context_text}\n{self.text}"
