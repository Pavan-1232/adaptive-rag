"""Locate evidence quotes in canonical text. Evidence is a character span, so it works for any
chunking. Matching ignores case and whitespace, and tolerates line-break hyphens in the quote."""

import re

_SPACE = re.compile(r"\s+")


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace and lowercase, keeping each output character's source position."""
    output: list[str] = []
    positions: list[int] = []
    previous_space = True
    for position, char in enumerate(text):
        if char.isspace():
            if not previous_space:
                output.append(" ")
                positions.append(position)
            previous_space = True
        else:
            lowered = char.lower()
            output.append(lowered if len(lowered) == 1 else char)
            positions.append(position)
            previous_space = False
    return "".join(output), positions


def locate_quote(
    text: str, quote: str, prefer: tuple[int, int] | None = None
) -> tuple[int, int] | None:
    """Return the quote's (start, end) in text, or None if it isn't there.

    The same table row can appear on several pages. With `prefer`, a character range such
    as the stated page, the first match that starts inside it wins; otherwise the first match.
    """
    needle = _SPACE.sub(" ", quote).strip().lower()
    if not needle:
        return None
    haystack, positions = _normalize_with_map(text)
    candidates = [needle, re.sub(r"(?<=[^\W\d_])- (?=[^\W\d_])", "", needle)]
    for candidate in candidates:
        first: tuple[int, int] | None = None
        found = haystack.find(candidate)
        while found >= 0:
            span = positions[found], positions[found + len(candidate) - 1] + 1
            if prefer is None or prefer[0] <= span[0] < prefer[1]:
                return span
            first = first or span
            found = haystack.find(candidate, found + 1)
        if first is not None:
            return first
    return None


def page_range(units: list, page: int | None) -> tuple[int, int] | None:
    """The character range of a physical page, from units given as objects or dicts."""
    if page is None:
        return None
    for unit in units:
        number, start, end = (
            (unit["number"], unit["start"], unit["end"])
            if isinstance(unit, dict)
            else (unit.number, unit.start, unit.end)
        )
        if number == page:
            return start, end
    return None


def overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))
