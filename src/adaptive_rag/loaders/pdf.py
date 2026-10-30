"""PDF extraction with pdfplumber. Assumes PDFs may be messy, scanned, or encrypted."""

import re
from collections import Counter
from pathlib import Path
from statistics import median

import pdfplumber

from .base import ExtractedDocument, ExtractionError, Unit, sections_from_headings

MIN_CHARS_PER_PAGE = 25
MAX_GARBLED_SHARE = 0.05
HEADING_SIZE_RATIO = 1.15
MAX_HEADING_CHARS = 120
MIN_PAGES_FOR_MARGIN_REMOVAL = 4
# pdfplumber's default of 3 glues words together in tightly set two-column papers.
X_TOLERANCE = 1
MIN_WORDS_FOR_COLUMNS = 50
MAX_CROSSING_SHARE = 0.03
MIN_COLUMN_SHARE = 0.2
GUTTER_SEARCH = (0.4, 0.6)
TITLE_BAND_SHARE = 0.4
BOLD_SHARE = 0.9
BOLD_FONT_MARKERS = ("bold", "black", "heavy", "demi", "medi", "semibold")
HYPHEN_BREAK = re.compile(r"[^\W\d_]-$")
MAX_BOLD_HEADING_CHARS = 80


def _find_columns(page) -> tuple[float, float] | None:
    """Return (gutter_x, columns_top) if the page has two columns, else None.

    A gutter is a vertical line that almost no word crosses. Full-width content such as a
    title is allowed above the columns, so crossings in the top band set where columns begin.
    """
    words = page.extract_words(x_tolerance=X_TOLERANCE)
    if len(words) < MIN_WORDS_FOR_COLUMNS:
        return None
    left, top, right, bottom = page.bbox
    width = right - left
    band_limit = top + (bottom - top) * TITLE_BAND_SHARE

    best = None
    for step in range(21):
        low, high = GUTTER_SEARCH
        gutter = left + width * (low + (high - low) * step / 20)
        crossing = [word for word in words if word["x0"] < gutter < word["x1"]]
        columns_top = max(
            (word["bottom"] for word in crossing if word["bottom"] <= band_limit), default=top
        )
        below = [word for word in words if word["top"] >= columns_top]
        crossed = sum(word["x0"] < gutter < word["x1"] for word in below)
        if not below:
            continue
        share = crossed / len(below)
        if best is None or share < best[0]:
            best = (share, gutter, columns_top, below)

    if best is None or best[0] > MAX_CROSSING_SHARE:
        return None
    _, gutter, columns_top, below = best
    left_words = sum(word["x1"] <= gutter for word in below)
    right_words = sum(word["x0"] >= gutter for word in below)
    if min(left_words, right_words) < len(below) * MIN_COLUMN_SHARE:
        return None
    return gutter, columns_top


def _page_lines(page) -> list[dict]:
    """Read a page in reading order: any full-width top band, then left, then right column."""
    # Rotated text is margin noise, such as arXiv's sidebar stamp, and reads backwards.
    page = page.filter(lambda obj: obj.get("object_type") != "char" or obj.get("upright", True))
    columns = _find_columns(page)
    if columns is None:
        return page.extract_text_lines(x_tolerance=X_TOLERANCE)
    gutter, columns_top = columns
    left, top, right, bottom = page.bbox
    regions = [(left, columns_top, gutter, bottom), (gutter, columns_top, right, bottom)]
    if columns_top > top:
        regions.insert(0, (left, top, right, columns_top))
    lines: list[dict] = []
    for region in regions:
        lines.extend(_region(page, region).extract_text_lines(x_tolerance=X_TOLERANCE))
    return lines


def _region(page, box: tuple[float, float, float, float]):
    """Keep characters centered in the box. Cropping would clip words at the edges."""
    x0, top, x1, bottom = box

    def inside(obj: dict) -> bool:
        if obj.get("object_type") != "char":
            return False
        return (
            x0 <= (obj["x0"] + obj["x1"]) / 2 < x1
            and top <= (obj["top"] + obj["bottom"]) / 2 < bottom
        )

    return page.filter(inside)


def _join_hyphenated(lines: list[dict]) -> list[dict]:
    """Repair words split across lines ("se-" + "mantic"), keeping the text searchable."""
    joined = [dict(line) for line in lines]
    for current, following in zip(joined, joined[1:], strict=False):
        text = current["text"].rstrip()
        if not HYPHEN_BREAK.search(text) or not following["text"][:1].islower():
            continue
        fragment, _, rest = following["text"].partition(" ")
        current["text"] = text[:-1] + fragment
        following["text"] = rest
    return [line for line in joined if line["text"].strip()]


def _margin_key(line: str) -> str:
    """Normalize digits so 'Page 3' and 'Page 4' count as the same running footer."""
    return re.sub(r"\d+", "#", line.strip().lower())


def _running_margin_lines(pages: list[list[dict]]) -> set[str]:
    """Find first or last lines that repeat on at least half the pages."""
    if len(pages) < MIN_PAGES_FOR_MARGIN_REMOVAL:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        if lines:
            counts.update({_margin_key(lines[0]["text"]), _margin_key(lines[-1]["text"])})
    return {key for key, count in counts.items() if count >= len(pages) / 2}


def _line_size(line: dict) -> float:
    sizes = [char["size"] for char in line.get("chars", []) if not char["text"].isspace()]
    return median(sizes) if sizes else 0.0


def _body_font_size(pages: list[list[dict]]) -> float:
    weights: Counter[float] = Counter()
    for lines in pages:
        for line in lines:
            weights[round(_line_size(line), 1)] += len(line["text"])
    return weights.most_common(1)[0][0] if weights else 0.0


def _is_bold_font(fontname: str) -> bool:
    return any(marker in fontname.lower() for marker in BOLD_FONT_MARKERS)


def _is_bold(line: dict) -> bool:
    chars = [char for char in line.get("chars", []) if not char["text"].isspace()]
    bold = sum(_is_bold_font(char.get("fontname", "")) for char in chars)
    return bool(chars) and bold / len(chars) >= BOLD_SHARE


def _is_heading(line: dict, body_size: float) -> bool:
    text = line["text"].strip()
    if not (
        body_size > 0
        and len(text) <= MAX_HEADING_CHARS
        and any(char.isalpha() for char in text)
        and not text.endswith((".", ",", ";"))
    ):
        return False
    size = _line_size(line)
    if size >= body_size * HEADING_SIZE_RATIO:
        return True
    # Many papers set section headings in bold at nearly body size.
    return _is_bold(line) and size >= body_size and len(text) <= MAX_BOLD_HEADING_CHARS


class PdfLoader:
    version = "pdf-4"

    def extract(self, path: Path) -> ExtractedDocument:
        try:
            with pdfplumber.open(path) as pdf:
                pages = [_page_lines(page) for page in pdf.pages]
        except Exception as exc:
            # pdfminer raises many exception types for corrupt or encrypted files.
            raise ExtractionError(
                "Could not read this PDF. It may be corrupt or password-protected."
            ) from exc
        return self._build(pages)

    def _build(self, pages: list[list[dict]]) -> ExtractedDocument:
        margins = _running_margin_lines(pages)
        body_size = _body_font_size(pages)

        parts: list[str] = []
        units: list[Unit] = []
        headings: list[tuple[str, int]] = []
        empty_pages: list[int] = []
        offset = 0

        for number, lines in enumerate(pages, start=1):
            kept = []
            for index, line in enumerate(lines):
                # A page's only line is body text, even if it repeats elsewhere.
                is_edge = len(lines) > 1 and index in (0, len(lines) - 1)
                if not (is_edge and _margin_key(line["text"]) in margins):
                    kept.append(line)
            if not kept:
                empty_pages.append(number)
                continue
            kept = _join_hyphenated(kept)

            page_start = offset
            for line in kept:
                if _is_heading(line, body_size):
                    headings.append((line["text"].strip(), offset))
                parts.append(line["text"])
                offset += len(line["text"]) + 1
            units.append(Unit(number, page_start, offset - 1))
            parts[-1] += "\n"  # Blank line between pages.
            offset += 1

        text = "\n".join(parts).rstrip()
        self._check_quality(text, len(pages))

        warnings = []
        if empty_pages:
            shown = ", ".join(str(page) for page in empty_pages[:20])
            warnings.append(f"No text on {len(empty_pages)} page(s), possibly scanned: {shown}")
        return ExtractedDocument(
            text=text,
            locator_kind="page",
            units=units,
            sections=sections_from_headings(headings, len(text)),
            warnings=warnings,
        )

    @staticmethod
    def _check_quality(text: str, page_count: int) -> None:
        if len(text) < MIN_CHARS_PER_PAGE * max(page_count, 1):
            raise ExtractionError(
                "Almost no text found. This PDF looks scanned and needs OCR, "
                "which is not supported yet."
            )
        garbled = text.count("(cid:") * len("(cid:0)") + text.count("�")
        if garbled / len(text) > MAX_GARBLED_SHARE:
            raise ExtractionError(
                "The text in this PDF is garbled because of its font encoding, "
                "so it would need OCR, which is not supported yet."
            )
