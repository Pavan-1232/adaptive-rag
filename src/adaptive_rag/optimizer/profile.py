"""Document profile: cheap statistics used to decide candidates now and config reuse later."""

import re
from dataclasses import asdict, dataclass
from statistics import median

from adaptive_rag.chunking import count_tokens, find_tables
from adaptive_rag.loaders import ExtractedDocument

PROFILE_VERSION = "profile-1"

# Reliable headings, for C5. Fixed by reasoning before any scoring (2026-11-04):
MIN_SECTIONS = 3  # fewer can't describe structure
MIN_SECTION_COVERAGE = 0.6  # most text must sit under some heading
MIN_MEDIAN_SECTION_TOKENS = 80  # many tiny sections means false headings (author lines, labels)
MAX_HEADING_WORDS = 15  # long "headings" are body text in a larger font

_ENGLISH = frozenset("the of and to in a is that for are on with as by be this it from or".split())


@dataclass(frozen=True)
class Profile:
    version: str
    format: str
    pages: int | None
    tokens: int
    sections: int
    heading_density: float  # sections per 1,000 tokens
    median_section_tokens: float
    section_coverage: float
    table_count: int
    table_share: float  # share of tokens inside detected tables
    chars_per_page: float | None
    language: str
    headings_reliable: bool
    has_tables: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _language(text: str) -> str:
    words = re.findall(r"[a-z]+", text[:200_000].lower())
    if not words:
        return "unknown"
    return "en" if sum(w in _ENGLISH for w in words) / len(words) >= 0.15 else "unknown"


def profile_document(doc: ExtractedDocument, fmt: str) -> Profile:
    tokens = count_tokens(doc.text)
    section_tokens = [count_tokens(doc.text[s.start : s.end]) for s in doc.sections]
    covered = sum(s.end - s.start for s in doc.sections) / len(doc.text) if doc.text else 0.0
    tables = find_tables(doc.text)
    table_tokens = sum(count_tokens(doc.text[t.start : t.end]) for t in tables)
    pages = len(doc.units) if doc.locator_kind == "page" else None
    median_tokens = median(section_tokens) if section_tokens else 0.0
    reliable = (
        len(doc.sections) >= MIN_SECTIONS
        and covered >= MIN_SECTION_COVERAGE
        and median_tokens >= MIN_MEDIAN_SECTION_TOKENS
        and all(len(s.heading.split()) <= MAX_HEADING_WORDS for s in doc.sections)
    )
    return Profile(
        version=PROFILE_VERSION,
        format=fmt,
        pages=pages,
        tokens=tokens,
        sections=len(doc.sections),
        heading_density=round(1000 * len(doc.sections) / tokens, 3) if tokens else 0.0,
        median_section_tokens=float(median_tokens),
        section_coverage=round(covered, 3),
        table_count=len(tables),
        table_share=round(table_tokens / tokens, 4) if tokens else 0.0,
        chars_per_page=round(len(doc.text) / pages, 1) if pages else None,
        language=_language(doc.text),
        headings_reliable=reliable,
        has_tables=bool(tables),
    )
