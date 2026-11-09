"""Answer-key linking: when the evidence holds an MCQ, add its answer key from the same document.

Real use (PROGRESS.md, 2026-11-09): ICAI study material puts the key in a separate "ANSWERS/HINTS
- Answers to the Multiple Choice Questions: 1. (a) 2. (b) ..." section pages after the questions,
and the key never mentions the question's words, so search doesn't find it. Approved design
change to both retrieval modes, behind the `answer_keys` setting (on by default).

The key used is the first answer-key heading after the question in the same document, with no
"TEST YOUR KNOWLEDGE" heading in between (that would start another set of questions). It's added
as a marked "answer_key" chunk, within the hard token maximum. Cross-document keys: future work.
"""

import re
from dataclasses import replace

from adaptive_rag.context import AppContext
from adaptive_rag.mcq import KEY_SECTION as _KEY_HEADING
from adaptive_rag.mcq import parse_key, visible_questions

from .baseline import _CHUNK_SELECT, _to_chunk, load_neighbor
from .types import RetrievedChunk

_NEW_SET = re.compile(r"test your knowledge", re.IGNORECASE)
_ASKED_NUMBER = re.compile(r"\b(?:question|q)\s*\.?\s*(?:no\.?\s*)?(\d{1,3})\b", re.IGNORECASE)
MAX_DOCUMENTS = 2  # MCQ documents linked per question; keeps the extra evidence small
MAX_KEY_CHUNKS = 3  # the heading's chunk plus up to two where the list runs on


def link_answer_keys(
    ctx: AppContext, used: list[RetrievedChunk], question: str, max_tokens: int
) -> tuple[list[RetrievedChunk], list[dict]]:
    """The evidence with answer-key chunks added, and what was linked (for traces and gate 4)."""
    have = {piece.chunk_id for chunk in used for piece in chunk.pieces}
    asked = _ASKED_NUMBER.search(question)
    evidence, links = list(used), []
    for document_id, pieces in list(_mcq_pieces(used).items())[:MAX_DOCUMENTS]:
        numbers, cut_off = set(), False
        for piece in pieces:
            found, tail = visible_questions(piece.text)
            numbers.update(number for number, _ in found)
            cut_off = cut_off or tail
        # Which MCQ the user means is certain only if they give its number, or exactly one MCQ
        # of this document is in view. Otherwise the key is still added, but gate 4 doesn't
        # compare the answer with any one keyed option (real use: AS 1, 2026-11-09).
        if asked:
            target = int(asked.group(1))
        elif len(numbers) == 1 and not cut_off:
            target = next(iter(numbers))
        else:
            target = None
        link = {
            "document_id": document_id,
            "questions_in_view": sorted(numbers),
            "question": target,
            "keyed": None,
        }
        first = min(pieces, key=lambda p: p.start_char)
        wanted = numbers | ({target} if target is not None else set())
        keys = _key_chunks(ctx, first, wanted)
        if not keys:
            links.append({**link, "added": [], "reason": "no answer key found"})
            continue
        keyed = _keyed_letter(keys, target)
        keys = [key for key in keys if key.chunk_id not in have]
        if not keys:
            links.append({**link, "keyed": keyed, "added": [], "reason": "already in evidence"})
            continue
        fitted, dropped = _fit(evidence, keys, max_tokens)
        if fitted is None:
            links.append({**link, "added": [], "reason": "over the token budget"})
            continue
        evidence = fitted
        have.update(key.chunk_id for key in keys)
        added = [key.chunk_id for key in keys]
        links.append({**link, "keyed": keyed, "added": added, "dropped": dropped})
    return evidence, links


def _mcq_pieces(used: list[RetrievedChunk]) -> dict[int, list[RetrievedChunk]]:
    """Every evidence piece showing a numbered MCQ, grouped by document in evidence order."""
    grouped: dict[int, list[RetrievedChunk]] = {}
    for chunk in used:
        for piece in chunk.pieces:
            if piece.source != "answer_key" and visible_questions(piece.text)[0]:
                grouped.setdefault(piece.document_id, []).append(piece)
    return grouped


def _key_chunks(ctx: AppContext, first: RetrievedChunk, wanted: set[int]) -> list[RetrievedChunk]:
    """The answer-key chunks for the set of questions that starts in or after `first`."""
    with ctx.db() as conn:
        rows = conn.execute(
            _CHUNK_SELECT + "c.document_id = ? AND c.start_char > ? AND (c.text LIKE ?"
            " OR c.text LIKE ? OR c.text LIKE ?) ORDER BY c.chunk_index",
            (
                first.document_id,
                first.start_char,
                "%multiple choice questions%",
                "%answers%hints%",
                "%test your knowledge%",
            ),
        ).fetchall()
    headings, new_sets = [], []
    for row in rows:
        for match in _KEY_HEADING.finditer(row["text"]):
            headings.append((row["start_char"] + match.start(), row))
        for match in _NEW_SET.finditer(row["text"]):
            new_sets.append(row["start_char"] + match.start())
    after = [(at, row) for at, row in headings if at > first.start_char]
    if not after:
        return []
    key_at = min(at for at, _ in after)
    if any(first.end_char < at < key_at for at in new_sets):
        return []  # the first key after the questions belongs to a later set of questions
    # Of the chunks holding that heading (chunks overlap), the one where it starts earliest.
    row = max((row for at, row in after if at == key_at), key=lambda r: r["start_char"])
    keys = [replace(_to_chunk(row, first.score), source="answer_key")]
    listed = parse_key(row["text"][key_at - row["start_char"] :])
    # A long key list can run on into the next chunks; follow it a little way.
    index = row["chunk_index"]
    while not wanted <= listed.keys() and len(keys) < MAX_KEY_CHUNKS:
        index += 1
        following = load_neighbor(ctx, first.document_id, index, first.score)
        if following is None or not parse_key(following.text):
            break
        keys.append(replace(following, source="answer_key"))
        listed = {**parse_key(following.text), **listed}
    return keys


def _keyed_letter(keys: list[RetrievedChunk], number: int | None) -> str | None:
    if number is None:
        return None
    text = keys[0].text
    heading = _KEY_HEADING.search(text)
    listed = parse_key(text[heading.start() :] if heading else text)
    for extra in keys[1:]:
        listed = {**parse_key(extra.text), **listed}
    return listed.get(number)


def _fit(
    evidence: list[RetrievedChunk], keys: list[RetrievedChunk], max_tokens: int
) -> tuple[list[RetrievedChunk] | None, list[str]]:
    """Add the keys; if over the maximum, drop the lowest-scored chunks without an MCQ or key."""
    kept = list(evidence)
    dropped = []
    need = sum(key.evidence_tokens for key in keys)
    while sum(c.evidence_tokens for c in kept) + need > max_tokens:
        droppable = [
            c
            for c in kept
            if c.source != "answer_key" and not any(visible_questions(p.text)[0] for p in c.pieces)
        ]
        if not droppable:
            return None, []
        lowest = min(droppable, key=lambda c: c.score)
        kept.remove(lowest)
        dropped.append(lowest.chunk_id)
    return kept + keys, dropped
