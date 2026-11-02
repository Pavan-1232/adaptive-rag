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
    source: Literal["direct", "expansion"] = "direct"
    start_char: int = 0
    end_char: int = 0
