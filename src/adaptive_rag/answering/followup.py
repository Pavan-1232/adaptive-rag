"""Follow-up questions in a chat: "what is the answer" or "explain it simply" after a question.

The chat sends the trace id of the previous turn. The server looks the trace up and uses it only
if it belongs to the same knowledge base, so a follow-up can never reach into another one. The
rules are plain word lists, no LLM call (query rewriting by an LLM is deferred, DESIGN.md):
- a follow-up has no words of its own beyond filler and reference words ("what is the answer",
  "explain it simply", "why?"), or starts with a continuation ("and question 2?", "what about
  part (b)?");
- anything with its own subject ("What is AS 3?") is a new question.
The search uses the base question (the first question of the chain) plus the follow-up, so a
chain of follow-ups never piles up. The previous answer is not used (traces don't store it).
"""

import re
import sqlite3
from dataclasses import dataclass

from adaptive_rag.context import AppContext

_WORD = re.compile(r"\w+")
_FILLER = frozenset(
    """
    a about again an and answer answers any are be briefly by can correct could detail detailed
    details do does elaborate english example examples explain explained final for further give
    go how i in into is it its just kindly last least let like make me mean meaning means more
    my now of ok okay on one option or plain please previous right say short shorter show
    simple simpler simply so solution solutions step steps sure tell terms than thanks that the
    them then there these they this those to understand us walk was we were what which why
    will with words would you your
    """.split()
)
_CONTINUATION = re.compile(r"^\s*(?:and|also|what about|how about|same for)\b", re.IGNORECASE)
SEPARATOR = " — "


def is_follow_up(question: str) -> bool:
    words = _WORD.findall(question.lower())
    if not words:
        return False
    return all(w in _FILLER for w in words) or bool(_CONTINUATION.match(question))


@dataclass(frozen=True)
class Resolved:
    question: str  # what the user typed
    searched: str  # what retrieval searched
    base: str  # first question of the chain
    follows_trace_id: int | None
    earlier: str | None  # the base question, shown to the model as context
    warning: str | None


def resolve(
    ctx: AppContext, kb: sqlite3.Row, question: str, previous_trace_id: int | None
) -> Resolved:
    standalone = Resolved(question, question, question, None, None, None)
    if previous_trace_id is None:
        return standalone
    with ctx.db() as conn:
        row = conn.execute(
            "SELECT kb_id, question, base_question FROM query_traces WHERE id = ?",
            (previous_trace_id,),
        ).fetchone()
    if row is None:
        warning = "The previous question wasn't found, so this was answered on its own."
        return Resolved(question, question, question, None, None, warning)
    if row["kb_id"] != kb["id"]:
        warning = (
            "The previous question belongs to another knowledge base, so this was answered "
            "on its own."
        )
        return Resolved(question, question, question, None, None, warning)
    if not is_follow_up(question):
        return standalone
    base = row["base_question"] or row["question"]
    return Resolved(question, base + SEPARATOR + question, base, previous_trace_id, base, None)
