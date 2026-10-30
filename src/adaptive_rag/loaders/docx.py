"""DOCX extraction. Word files have no reliable page numbers, so locators are paragraphs."""

from pathlib import Path

import docx
from docx.table import Table

from .base import ExtractedDocument, ExtractionError, Unit, sections_from_headings


def _is_heading(style_name: str | None) -> bool:
    return bool(style_name) and (style_name.startswith("Heading") or style_name == "Title")


class DocxLoader:
    version = "docx-1"

    def extract(self, path: Path) -> ExtractedDocument:
        try:
            document = docx.Document(str(path))
            blocks = list(document.iter_inner_content())
        except Exception as exc:
            raise ExtractionError("Could not read this DOCX file. It may be corrupt.") from exc

        parts: list[str] = []
        units: list[Unit] = []
        headings: list[tuple[str, int]] = []
        offset = 0
        number = 0

        for block in blocks:
            if isinstance(block, Table):
                rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in block.rows]
                content = "\n".join(rows).strip()
                is_heading = False
            else:
                content = block.text.strip()
                is_heading = _is_heading(block.style.name if block.style else None)
            if not content:
                continue
            number += 1
            if is_heading:
                headings.append((content, offset))
            parts.append(content)
            units.append(Unit(number, offset, offset + len(content)))
            offset += len(content) + 2

        text = "\n\n".join(parts)
        if not text:
            raise ExtractionError("This DOCX file contains no text.")
        return ExtractedDocument(
            text=text,
            locator_kind="paragraph",
            units=units,
            sections=sections_from_headings(headings, len(text)),
        )
