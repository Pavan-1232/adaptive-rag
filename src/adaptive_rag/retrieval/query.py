"""Rule-based query analysis: question type and, for multi-part questions, its parts.

No LLM call. The rules are deliberately simple and readable; they are judged by how they
change retrieval on dev questions, not by how clever they look. A wrong split is cheap,
because the full question is always searched as well.
"""

import re
from dataclasses import dataclass
from typing import Literal

QueryKind = Literal["factual", "table", "multi_part", "broad"]

# Words that start a new clause after "and" or a comma: "..., and how long does it ...".
_CLAUSE_START = (
    r"(?:how|what|which|where|when|why|who|whose|does|do|did|is|are|was|were|has|have|had"
    r"|can|could|should|would|will)"
)
_SPLITTERS = [
    re.compile(r",?\s+while also\s+", re.IGNORECASE),
    re.compile(r",?\s+as well as\s+(?=" + _CLAUSE_START + r"\b)", re.IGNORECASE),
    re.compile(r",?\s+and also\s+", re.IGNORECASE),
    re.compile(r"(?:,\s*|\s+)and\s+(?=" + _CLAUSE_START + r"\b)", re.IGNORECASE),
    re.compile(r",\s+and\s+", re.IGNORECASE),
    re.compile(r",\s+(?=" + _CLAUSE_START + r"\b)", re.IGNORECASE),
]
_COMPARE = re.compile(r"^\s*compare\s+(.+?)\s+(?:with|to|against|and)\s+(.+?)[.?]?\s*$", re.I)
_TABLE_WORDS = re.compile(
    r"\b(how much|how many|percent|percentage|rate|ratio|total|median|projection|"
    r"revenue|income|cost|margin|figure|number|amount|billion|million|table|row|column)\b",
    re.IGNORECASE,
)
_BROAD_WORDS = re.compile(r"\b(overview|summari[sz]e|main (?:themes|points)|in general)\b", re.I)
MIN_PART_WORDS = 4
_STARTS_LIKE_QUESTION = re.compile(
    r"^\s*(?:" + _CLAUSE_START + r"|compare|give|list|name|describe|explain)\b", re.I
)


@dataclass(frozen=True)
class QueryPlan:
    kind: QueryKind
    parts: tuple[str, ...]  # one entry, the question itself, when it isn't split


def _clean(part: str) -> str:
    part = part.strip(" ,;:")
    return part[0].upper() + part[1:] if part else part


def _split_sentence(sentence: str) -> list[str]:
    pieces = [sentence]
    for pattern in _SPLITTERS:
        next_pieces: list[str] = []
        for piece in pieces:
            next_pieces.extend(pattern.split(piece))
        pieces = next_pieces
    pieces = [p for p in (_clean(p) for p in pieces) if p]
    # A lead-in such as "In the December 2024 projections" or "If not" belongs to what follows.
    merged: list[str] = []
    carry = ""
    for index, piece in enumerate(pieces):
        piece = f"{carry} {piece[0].lower()}{piece[1:]}".strip() if carry else piece
        carry = ""
        if index < len(pieces) - 1 and not _STARTS_LIKE_QUESTION.match(piece):
            carry = piece + ","
            continue
        merged.append(_clean(piece))
    return merged


def split_parts(question: str) -> list[str]:
    """Split into parts at question marks and clause boundaries. Tiny fragments are merged
    back into the part before them, so a split never produces a part like "and why"."""
    match = _COMPARE.match(question)
    if match:
        return [_clean(match.group(1)), _clean(match.group(2))]

    # A colon after a short lead-in ("The labor picture: where ..., where ...") is a header.
    head, sep, rest = question.partition(":")
    if sep and len(head.split()) <= 4 and rest.strip():
        question = rest

    sentences = [s for s in re.split(r"(?<=\?)\s+", question.strip()) if s.strip()]
    parts: list[str] = []
    for sentence in sentences:
        for piece in _split_sentence(sentence):
            if parts and len(piece.split()) < MIN_PART_WORDS:
                parts[-1] = f"{parts[-1]} {piece}"
            else:
                parts.append(piece)
    if len(parts) > 1 and len(parts[0].split()) < MIN_PART_WORDS:
        parts[1] = f"{parts[0]} {parts[1]}"
        parts.pop(0)
    return parts or [question.strip()]


def analyze(question: str, split: bool = True) -> QueryPlan:
    parts = split_parts(question) if split else [question.strip()]
    if len(parts) > 1:
        return QueryPlan("multi_part", tuple(parts))
    if _BROAD_WORDS.search(question):
        return QueryPlan("broad", (question.strip(),))
    if _TABLE_WORDS.search(question):
        return QueryPlan("table", (question.strip(),))
    return QueryPlan("factual", (question.strip(),))
