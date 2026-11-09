"""Answer-key linking (retrieval/answer_keys.py) and gate 4 with a linked key.

The documents are made up, in the layout of a study-material unit: TEST YOUR KNOWLEDGE, numbered
MCQs, theory pages, then ANSWERS/HINTS with "Answers to the Multiple Choice Questions: 1. (a) ...".
"""

import pytest

from adaptive_rag.answering import answer_question
from adaptive_rag.evaluation.runner import resume_conflicts
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.mcq import KEY_MISMATCH_MESSAGE, parse_key, visible_questions
from adaptive_rag.retrieval import RetrievedChunk, retrieve_evidence
from adaptive_rag.retrieval.answer_keys import link_answer_keys

QUESTIONS = (
    "TEST YOUR KNOWLEDGE\nMultiple Choice Questions\n"
    "1. Vega Ltd. paid income tax of 12,000 on its operating profit and cannot link it to any "
    "investing or financing item. Under which activity is it shown in the cash flow statement?\n"
    "(a) Operating activities\n(b) Investing activities\n(c) Financing activities\n"
    "(d) Not shown\n"
    "2. Interest received by a manufacturing company on a fixed deposit is shown as\n"
    "(a) operating cash inflow\n(b) investing cash inflow\n(c) financing cash inflow\n"
    "(d) cash equivalent\n\n"
)
KEY = "ANSWERS/HINTS\nAnswers to the Multiple Choice Questions\n1. (a) 2. (b)\n\n"


def filler(topic: str, n: int = 40) -> str:
    """Theory text: it shares a few words with the question, so search ranks it above the key."""
    return f"{topic} notes on the cash flow statement and inventory valuation. " * n + "\n\n"


def unrelated(n: int = 30) -> str:
    """Text before a key that shares nothing with the questions, so search never finds the key."""
    return "Appendix glossary of unrelated terms. " * n + "\n\n"


VEGA = (
    "Vega Ltd. paid income tax of 12,000 on its operating profit and cannot link it to investing "
    "or financing: under which activity is it shown in the cash flow statement?"
)


@pytest.fixture
def make_kb(ctx, tmp_path):
    ctx.settings.chunk_size_tokens = 200
    ctx.settings.chunk_overlap_tokens = 10
    ctx.settings.top_k = 1  # only the best chunk, so the key is never found by search

    def make(text: str):
        kb = create_knowledge_base(ctx, "CA")
        path = tmp_path / "unit.txt"
        path.write_text(text)
        _, job_id, _ = register_upload(ctx, kb, path, "study_unit_4.txt")
        run_ingest_job(ctx, job_id)
        return kb

    return make


def added_keys(evidence):
    return [chunk for chunk in evidence.used if chunk.source == "answer_key"]


@pytest.mark.parametrize("mode", ["baseline", "adaptive"])
def test_key_after_the_questions_is_added(ctx, make_kb, mode):
    ctx.settings.retrieval = mode
    kb = make_kb(
        filler("Opening") + QUESTIONS + filler("Theory") + unrelated() + KEY + filler("Closing")
    )
    evidence = retrieve_evidence(ctx, kb, VEGA)
    keys = added_keys(evidence)
    assert len(keys) == 1 and "Answers to the Multiple Choice Questions" in keys[0].text
    [link] = evidence.info["answer_keys"]
    # Questions 1 and 2 are both in view and no number was given: key added, no keyed option.
    assert link["questions_in_view"] == [1, 2]
    assert link["question"] is None and link["keyed"] is None
    assert sum(c.evidence_tokens for c in evidence.used) <= ctx.settings.evidence_max_tokens


def test_question_number_in_the_question_wins(ctx, make_kb):
    kb = make_kb(filler("Opening") + QUESTIONS + filler("Theory") + unrelated() + KEY)
    evidence = retrieve_evidence(ctx, kb, "Vega Ltd cash flow: what's the answer to question 2?")
    [link] = evidence.info["answer_keys"]
    assert link["question"] == 2 and link["keyed"] == "b"


def test_no_key_in_the_document(ctx, make_kb):
    kb = make_kb(filler("Opening") + QUESTIONS + filler("Theory"))
    evidence = retrieve_evidence(ctx, kb, VEGA)
    assert added_keys(evidence) == []
    assert evidence.info["answer_keys"][0]["reason"] == "no answer key found"


def test_key_of_a_later_set_is_not_used(ctx, make_kb):
    later = "Chapter 5\nTEST YOUR KNOWLEDGE\nMultiple Choice Questions\n" + filler("Other", 5)
    kb = make_kb(QUESTIONS + filler("Theory") + later + unrelated() + KEY)
    evidence = retrieve_evidence(ctx, kb, VEGA)
    assert added_keys(evidence) == []


def test_key_split_over_two_chunks(ctx, make_kb):
    many = " ".join(f"{n}. ({'abcd'[n % 4]})" for n in range(1, 61))
    numbered = QUESTIONS.replace("1. Vega", "57. Vega")
    kb = make_kb(numbered + filler("Theory") + "ANSWERS/HINTS\n" + many + "\n\n" + filler("End"))
    evidence = retrieve_evidence(ctx, kb, VEGA + " (question 57)")
    keys = added_keys(evidence)
    assert len(keys) >= 2  # the heading's chunk, then the list followed until 57 appears
    assert 57 not in parse_key(keys[0].text) and 57 in parse_key(keys[-1].text)
    assert evidence.info["answer_keys"][0]["keyed"] == "abcd"[57 % 4]


def test_budget_drops_a_non_mcq_chunk_or_skips(ctx, make_kb):
    kb = make_kb(filler("Opening") + QUESTIONS + filler("Theory") + unrelated() + KEY)
    ctx.settings.top_k = 3
    base = retrieve_evidence(ctx, kb, VEGA)
    key_tokens = added_keys(base)[0].evidence_tokens
    without_key = sum(c.evidence_tokens for c in base.used) - key_tokens

    ctx.settings.evidence_max_tokens = without_key + key_tokens - 1  # one token short
    tight = retrieve_evidence(ctx, kb, VEGA)
    assert len(added_keys(tight)) == 1 and tight.info["answer_keys"][0]["dropped"]
    assert sum(c.evidence_tokens for c in tight.used) <= ctx.settings.evidence_max_tokens

    ctx.settings.top_k = 1
    question_tokens = base.used[0].evidence_tokens  # the MCQ chunk, ranked first
    ctx.settings.evidence_max_tokens = question_tokens  # room for the question, not the key
    starved = retrieve_evidence(ctx, kb, VEGA)
    assert added_keys(starved) == []
    assert starved.info["answer_keys"][0]["reason"] == "over the token budget"


def test_setting_off(ctx, make_kb):
    ctx.settings.answer_keys = False
    kb = make_kb(filler("Opening") + QUESTIONS + filler("Theory") + unrelated() + KEY)
    evidence = retrieve_evidence(ctx, kb, VEGA)
    assert added_keys(evidence) == [] and "answer_keys" not in evidence.info


def test_answer_cites_the_key_and_a_wrong_option_is_withheld(ctx, make_kb):
    kb = make_kb(filler("Opening") + QUESTIONS + filler("Theory") + unrelated() + KEY)
    asked = VEGA + " This is question 1."
    ctx.llm.queue(answer="Question 1: (a) Operating activities [E1, E2].", cited_ids=["E1", "E2"])
    result = answer_question(ctx, kb, asked)
    assert result.status == "answered"
    assert [c.source for c in result.citations] == ["direct", "answer_key"]

    ctx.llm.queue(answer="Question 1: (c) Financing activities [E1, E2].", cited_ids=["E1", "E2"])
    result = answer_question(ctx, kb, asked)
    assert result.status == "partial" and result.answer == KEY_MISMATCH_MESSAGE


def test_eval_runs_record_the_setting_and_old_runs_count_as_without():
    old = {"retrieval": "baseline"}  # saved before answer_keys existed
    assert resume_conflicts(old, {"retrieval": "baseline", "answer_keys": False}) == []
    assert resume_conflicts(old, {"retrieval": "baseline", "answer_keys": True}) == ["answer_keys"]


# Real-use bug (2026-11-09): two questions on an accounting-policies unit were withheld as "didn't
# match the linked key". The linker looked only at the first MCQ chunk (Q5's tail, Q6, Q7 cut
# off), matched Q6 by shared words and keyed (c). Made-up unit in that layout: a key grid, no dots.
UNIT1 = (
    "TEST YOUR KNOWLEDGE\nMultiple Choice Questions\n"
    "1. Which of the following is NOT a step in preparing a bank reconciliation statement?\n"
    "(a) Comparing deposits\n(b) Declaring dividends\n(c) Listing unpresented cheques\n"
    "(d) Adjusting bank charges\n"
    "2. Two branches of one firm use different depreciation methods for identical machines. "
    "Which need of the readers suffers most?\n(a) Comparing the branches\n(b) Timeliness\n"
    "(c) Verifiability\n(d) Brevity\n"
    + "".join(
        f"{n}. Filler question {n} about disclosure.\n(a) One\n(b) Two\n(c) Three\n(d) Four\n"
        for n in (3, 4)
    )
    + "5. Must a change of method required by a new rule be explained further?\n"
    "(a) Yes, always.\n(b) No, the rule is reason enough.\n"
    "(c) No, such changes need no note at all.\n(d) Yes, and every prior year is redone.\n"
    "6. Atlas Ltd. sets aside an amount for a likely repair claim but does not record a refund "
    "it only hopes for. Which idea in choosing a method does this reflect?\n(a) Materiality\n"
    "(b) Substance over form\n(c) Prudence\n(d) Consistency\n"
    "7. Two firms in one trade value stock by different methods, so their profits differ. What "
    "becomes harder for readers?\n(a) Checking the arithmetic.\n"
    "(b) Comparing the firms; disclosing the methods used helps.\n"
    "(c) Reading the notes.\n(d) Finding the auditor.\n\n"
)
UNIT1_KEY = (
    "ANSWERS/HINTS\nAnswers to the Multiple Choice Questions\n"
    "1 (b) 2 (a) 3 (c) 4 (d)\n5 (b) 6 (c) 7 (b)\n\n"
)
UNIT1_Q_COMPARE = (
    "Which need of the readers suffers most when two branches of one firm use different "
    "depreciation methods, as per the Unit 1 MCQ? Give the correct option."
)
UNIT1_Q_NOT_A_STEP = (
    "Which is NOT a step in preparing a bank reconciliation statement, according to the Unit 1 MCQ?"
)


def test_key_grid_without_dots():
    assert parse_key("1 (b) 2 (a) 3 (c) 4 (d)\n5 (b) 6 (c) 7 (b)") == {
        1: "b",
        2: "a",
        3: "c",
        4: "d",
        5: "b",
        6: "c",
        7: "b",
    }


def unit1_piece(document, start_marker: str, end_marker: str) -> RetrievedChunk:
    """Evidence cut from the indexed unit text, like a real chunk boundary."""
    start, end = document.index(start_marker), document.index(end_marker) + len(end_marker)
    return RetrievedChunk(
        f"piece-{start}",
        1,
        "study_unit_1.txt",
        0,
        document[start:end],
        150,
        0.6,
        "line",
        1,
        1,
        None,
        start_char=start,
        end_char=end,
    )


@pytest.mark.parametrize("question", [UNIT1_Q_COMPARE, UNIT1_Q_NOT_A_STEP])
def test_unit1_questions_are_not_matched_to_the_wrong_mcq(ctx, make_kb, question):
    document = filler("Theory") + UNIT1 + filler("Theory") + unrelated() + UNIT1_KEY
    make_kb(document)
    # Like the real traces: first the chunk with Q5's tail, Q6 and the start of Q7, then (for the
    # NOT-a-step question) the chunk with Q1 and Q2.
    q6 = unit1_piece(document, "(c) No, such changes", "(b) Comparing the firms;")
    found, cut_off = visible_questions(q6.text)
    assert [number for number, _ in found] == [6, 7] and cut_off  # 7 runs past the end
    used = [q6]
    if question == UNIT1_Q_NOT_A_STEP:
        used.append(unit1_piece(document, "1. Which", "(d) Brevity"))
    evidence, [link] = link_answer_keys(ctx, used, question, 4000)
    assert link["question"] is None and link["keyed"] is None  # ambiguous: never guessed
    assert len(evidence) == len(used) + 1  # the key is still added for the model to read


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (UNIT1_Q_COMPARE, "Question 2: (a) Comparing the branches [E1, E2]."),
        (UNIT1_Q_NOT_A_STEP, "Question 1: (b) Declaring dividends [E1, E2]."),
    ],
)
def test_unit1_correct_options_are_not_withheld(ctx, make_kb, question, answer):
    kb = make_kb(filler("Theory") + UNIT1 + filler("Theory") + unrelated() + UNIT1_KEY)
    ctx.llm.queue(answer=answer, cited_ids=["E1", "E2"])
    result = answer_question(ctx, kb, question)
    assert result.status == "answered", result.warnings
    assert result.answer != KEY_MISMATCH_MESSAGE


def test_explicit_number_still_checks_the_key(ctx, make_kb):
    kb = make_kb(filler("Theory") + UNIT1 + filler("Theory") + unrelated() + UNIT1_KEY)
    ctx.llm.queue(answer="Question 2: (b) Timeliness [E1, E2].", cited_ids=["E1", "E2"])
    result = answer_question(ctx, kb, "In the Unit 1 MCQs, what is the answer to question 2?")
    assert result.status == "partial" and result.answer == KEY_MISMATCH_MESSAGE
