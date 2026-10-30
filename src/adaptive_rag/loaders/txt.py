"""Plain text extraction. Locators are line numbers in the normalized text."""

import re
from pathlib import Path

from .base import ExtractedDocument, ExtractionError, Unit, sections_from_headings

MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(\S.*)$")
MAX_CAPS_HEADING_CHARS = 80


def _heading(line: str) -> str | None:
    stripped = line.strip()
    match = MARKDOWN_HEADING.match(stripped)
    if match:
        return match.group(1).strip()
    if 3 <= len(stripped) <= MAX_CAPS_HEADING_CHARS and stripped.isupper():
        return stripped
    return None


class TxtLoader:
    version = "txt-1"

    def extract(self, path: Path) -> ExtractedDocument:
        raw = path.read_bytes()
        warnings: list[str] = []
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = raw.decode("cp1252", errors="replace")
            warnings.append("File is not UTF-8; decoded as Windows-1252.")
        text = decoded.replace("\r\n", "\n").replace("\r", "\n").rstrip()
        if not text.strip():
            raise ExtractionError("This text file is empty.")

        units: list[Unit] = []
        headings: list[tuple[str, int]] = []
        offset = 0
        for number, line in enumerate(text.split("\n"), start=1):
            if line.strip():
                units.append(Unit(number, offset, offset + len(line)))
                heading = _heading(line)
                if heading:
                    headings.append((heading, offset))
            offset += len(line) + 1
        return ExtractedDocument(
            text=text,
            locator_kind="line",
            units=units,
            sections=sections_from_headings(headings, len(text)),
            warnings=warnings,
        )
