"""Multiple-choice questions: option parsing, the after-generation check, answer-key parsing.

Code check after generation: the model may not pick an MCQ option the evidence never confirms.

The prompt rule alone wasn't enough in real use (PROGRESS.md, 2026-11-09): Gemini still picked an
option when the evidence had options but no answer key. This is a heuristic, kept narrow:
- only complete (a)-(d) option sets count as an MCQ, and not clause lists whose items end in
  ";", "; and" or "or" (statutes, certifications);
- a pick is a standalone letter ("(c)", "option c"), or reproducing an option's text (runs of 5
  words; the whole text for options of 3-4 words) where most reproduced runs appear nowhere in the
  evidence outside the options;
- any answer-key marker in the evidence turns the check off, and so does an answer that already
  says the option isn't given.
"""

import re

NOT_GIVEN_MESSAGE = (
    "The correct option isn't given in the documents. The cited passage shows the question and "
    "its options, but no answer key or solution."
)
NOT_GIVEN_WARNING = (
    "The model picked a multiple-choice option, but the evidence has no answer key, "
    "so the pick was withheld."
)

KEY_MISMATCH_MESSAGE = (
    "The model's choice didn't match the answer key in the documents, so it was withheld. "
    "See the cited answer key."
)
KEY_MISMATCH_WARNING = "The model picked an option that differs from the linked answer key."

_MARKER = re.compile(r"\(([a-dA-D])\)|(?:^|\n)[ \t]*([a-dA-D])[.)][ \t]")
# Where option (d)'s text ends: the next numbered question or a blank line.
_END_OF_D = re.compile(r"\n\s*(?:\d{1,3}[.)\s]|Q\.?\s*\d)|\n\s*\n")
# Clause lists ("(a) Designed such controls...; (b) ...; and") end items like this; options don't.
_CLAUSE_END = re.compile(r"(?:;|;\s*(?:and|or)|\b(?:and|or))\s*$", re.IGNORECASE)
_MAX_GAP = 600  # characters between options; farther apart means a different block
_KEY = re.compile(
    r"answers?\s*(?:/\s*hints|key|to the multiple choice)"
    r"|\bans(?:wer)?\s*[.:\-]?\s*[:\-]?\s*\(?[a-d]\)"
    r"|correct (?:answer|option)\s*(?:is|:)",
    re.IGNORECASE,
)
_ALREADY_DECLINED = re.compile(r"\b(?:not|isn't|is not) (?:given|stated|provided)\b", re.IGNORECASE)
_LETTER_PICK = re.compile(r"(?<![\w)])\(([a-dA-D])\)|\boption\s*\(?([a-dA-D])\b", re.IGNORECASE)
_SHINGLE = 5


def option_blocks(text: str) -> list[dict[str, tuple[int, int]]]:
    """Complete (a)-(d) option sets: letter -> (start, end) of the option's text."""
    blocks, current, expected, last_end = [], {}, "a", 0
    for match in _MARKER.finditer(text):
        letter, (start, end) = (match.group(1) or match.group(2)).lower(), match.span()
        if current and start - last_end > _MAX_GAP:
            current, expected = {}, "a"
        if letter != expected:
            continue  # e.g. "(c) Both (a) and (b)": references inside an option are text
        if current:
            previous = chr(ord(letter) - 1)
            current[previous] = (current[previous][0], start)
        current[letter] = (end, end)
        last_end = end
        if letter == "d":
            stop = _END_OF_D.search(text, end)
            current["d"] = (end, stop.start() if stop else min(len(text), end + 400))
            clause_ends = sum(bool(_CLAUSE_END.search(text[a:b])) for a, b in current.values())
            if clause_ends < 2:
                blocks.append(current)
            current, expected = {}, "a"
        else:
            expected = chr(ord(letter) + 1)
    return blocks


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _letter_options(evidence_texts: list[str]) -> tuple[list[tuple[str, str]], str]:
    """(letter, option text) for every option set, and all evidence text outside the options."""
    options, outside = [], []
    for text in evidence_texts:
        blocks = option_blocks(text)
        spans = sorted((span, letter) for block in blocks for letter, span in block.items())
        options += [(letter, text[start:end]) for (start, end), letter in spans]
        cursor = 0
        for (start, end), _ in spans:
            outside.append(text[cursor:start])
            cursor = end
        outside.append(text[cursor:])
    return options, " ".join(outside)


def picked_letters(answer: str, evidence_texts: list[str]) -> set[str]:
    """Option letters the answer names, or whose text it reproduces without other support."""
    options, outside = _letter_options(evidence_texts)
    if not options:
        return set()
    picked = {(m.group(1) or m.group(2)).lower() for m in _LETTER_PICK.finditer(answer)}
    said, grounded = _words(answer), _words(outside)
    for letter, option in options:
        words = _words(option)
        if len(words) < 3:
            continue  # "Nil", "MCA": too short to tell a pick from a coincidence; letters only
        size = min(_SHINGLE, len(words))
        shingles = [words[i : i + size] for i in range(len(words) - size + 1)]
        reproduced = [sh for sh in shingles if _contains(said, sh)]
        ungrounded = [sh for sh in reproduced if not _contains(grounded, sh)]
        # Mostly found only in the option: a pick. Mostly found elsewhere too: a grounded claim.
        if reproduced and len(ungrounded) * 2 > len(reproduced):
            picked.add(letter)
    return picked


def picks_unkeyed_option(answer: str, evidence_texts: list[str]) -> bool:
    """True if the answer picks an MCQ option and nothing in the evidence says which is right."""
    if _ALREADY_DECLINED.search(answer) or any(_KEY.search(t) for t in evidence_texts):
        return False
    return bool(picked_letters(answer, evidence_texts))


def contradicts_key(answer: str, evidence_texts: list[str], keyed: set[str]) -> bool:
    """True if the answer picks options but none of them is the one the linked key gives."""
    picked = picked_letters(answer, evidence_texts)
    return bool(picked) and not picked & keyed


# Answer-key linking (retrieval/answer_keys.py) uses these too.
_QUESTION_NUMBER = re.compile(r"(?:^|\n)[ \t]*(?:Q\.?\s*)?(\d{1,3})[.)]?[ \t]")
_KEY_ITEM = re.compile(r"(?<![\d.])(\d{1,3})\s*[.)]?\s*\(([a-dA-D])\)")


KEY_SECTION = re.compile(
    r"answers? to the multiple choice questions|answers\s*/\s*hints", re.IGNORECASE
)


def visible_questions(text: str) -> tuple[list[tuple[int, int]], bool]:
    """Numbered MCQs whose options start in this text, even if they run past its end, as
    (number, position); and whether options of an unnumbered question show first (the tail of a
    question cut off at the start of a chunk). Text after an answer-key heading is ignored."""
    heading = KEY_SECTION.search(text)
    text = text[: heading.start()] if heading else text
    numbers = list(_QUESTION_NUMBER.finditer(text))
    found = []
    for i, number in enumerate(numbers):
        stop = numbers[i + 1].start() if i + 1 < len(numbers) else len(text)
        first = _MARKER.search(text, number.end(), min(stop, number.end() + 800))
        if first and (first.group(1) or first.group(2)).lower() == "a":
            found.append((int(number.group(1)), number.start()))
    before = text[: numbers[0].start()] if numbers else text
    letters = {(m.group(1) or m.group(2)).lower() for m in _MARKER.finditer(before)}
    return found, len(letters) >= 2


def option_text(evidence_texts: list[str], number: int, letter: str) -> str | None:
    """The text of option `letter` of question `number`, from the evidence, on one line."""
    for text in evidence_texts:
        for block in option_blocks(text):
            start = block["a"][0]
            numbers = list(_QUESTION_NUMBER.finditer(text, max(0, start - 800), start))
            if numbers and int(numbers[-1].group(1)) == number and letter in block:
                a, b = block[letter]
                option = " ".join(text[a:b].split())
                return option[:150] or None
    return None


def restate_option(answer: str, letter: str, text: str) -> str:
    """Add the option's text after its letter when the answer gives the letter alone:
    "1. (a)" -> "1. (a) Nil". Unchanged if the text is already there or the letter isn't."""
    if " ".join(text.lower().split()) in " ".join(answer.lower().split()):
        return answer
    marker = re.compile(rf"(?<![\w)])\({letter}\)", re.IGNORECASE)
    return marker.sub(lambda m: f"{m.group(0)} {text}", answer, count=1)


def parse_key(text: str) -> dict[int, str]:
    """Question number -> keyed letter from a list like "1. (a) 2. (b) ... 6 (a) 7 (b)"."""
    return {int(m.group(1)): m.group(2).lower() for m in _KEY_ITEM.finditer(text)}
