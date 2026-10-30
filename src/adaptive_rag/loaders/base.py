"""The loader interface. Every format produces one canonical text plus offset maps."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

LocatorKind = Literal["page", "paragraph", "line"]


class ExtractionError(Exception):
    """The file is valid but no usable text could be extracted. The message is user-facing."""


@dataclass(frozen=True)
class Unit:
    """A page, paragraph, or line, as a character range in the canonical text."""

    number: int
    start: int
    end: int


@dataclass(frozen=True)
class Section:
    heading: str
    start: int
    end: int


@dataclass
class ExtractedDocument:
    text: str
    locator_kind: LocatorKind
    units: list[Unit]
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Loader(Protocol):
    version: str

    def extract(self, path: Path) -> ExtractedDocument: ...


def sections_from_headings(headings: list[tuple[str, int]], text_length: int) -> list[Section]:
    """Each section runs from its heading to the next heading, or the end of the text."""
    if not headings:
        return []
    ends = [start for _, start in headings[1:]] + [text_length]
    return [
        Section(heading, start, end) for (heading, start), end in zip(headings, ends, strict=True)
    ]
