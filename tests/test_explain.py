"""Opt-in tutor explanation (answering/explain.py): it can never change the grounded answer."""

import json

import pytest
from fastapi.testclient import TestClient

from adaptive_rag.answering import INSUFFICIENT_MESSAGE, GenerationFailed, answer_question
from adaptive_rag.answering.answer import CloudNotAllowed
from adaptive_rag.answering.explain import LABEL, LABEL_UNVERIFIED
from adaptive_rag.api import create_app
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.mcq import NOT_GIVEN_MESSAGE
from adaptive_rag.providers import ProviderUnavailable

DOC = "Vega Ltd. reports income tax paid on operating profit under operating activities.\n"
QUESTION = "Under which activity does Vega Ltd report income tax paid?"
MCQ = (
    "07 Source: Study Unit 4, Practice Q.7\n"
    "Is a lender a related party merely because it lends on normal terms?\n"
    "(a) Yes, always.\n(b) Yes, if the loan is large.\n"
    "(c) No - providers of finance are not related parties merely because of those dealings.\n"
    "(d) No, AS 18 covers only individuals.\n"
)
TUTOR = "Income tax usually counts as operating because it comes from the main business [E1]."


@pytest.fixture
def kb(ctx, tmp_path):
    knowledge_base = create_knowledge_base(ctx, "KB")
    for name, text in (("report.txt", DOC), ("bank.txt", MCQ)):
        path = tmp_path / name
        path.write_text(text)
        _, job_id, _ = register_upload(ctx, knowledge_base, path, name)
        run_ingest_job(ctx, job_id)
    return knowledge_base


def grounded(result):
    return (result.status, result.answer, result.citations, result.warnings, result.trace_id > 0)


def test_explain_off_or_on_gives_the_same_grounded_result(ctx, kb):
    ctx.llm.queue(answer="Operating activities [E1].")
    off = answer_question(ctx, kb, QUESTION)
    ctx.llm.queue(answer="Operating activities [E1].")
    ctx.llm.responses.append(TUTOR)
    on = answer_question(ctx, kb, QUESTION, explain=True)
    assert grounded(off)[:4] == grounded(on)[:4]
    assert off.explanation is None and off.explanation_label is None
    assert on.explanation_label == LABEL
    # Citation markers are removed and never become citations.
    assert (
        on.explanation
        == "Income tax usually counts as operating because it comes from the main business."
    )
    assert len(on.citations) == len(off.citations)


def test_the_explanation_prompt_has_no_evidence_and_gets_the_final_answer(ctx, kb):
    # Gate 4 withholds the pick; the explanation call must see the withheld answer, not "(c)".
    ctx.llm.queue(answer="(c) No - providers of finance are not related parties [E1].")
    ctx.llm.responses.append("General idea: lenders are not related parties by lending alone.")
    result = answer_question(
        ctx,
        kb,
        "Is a lender a related party merely because it lends on normal terms?",
        explain=True,
    )
    assert result.status == "partial" and result.answer == NOT_GIVEN_MESSAGE  # grounded unchanged
    assert result.explanation_label == LABEL_UNVERIFIED
    system, user = (m["content"] for m in ctx.llm.calls[-1])
    assert "<evidence" not in system + user
    assert "You do not have the user's documents" in system
    assert NOT_GIVEN_MESSAGE.split(".")[0] in user and "(c) No - providers" not in user


def test_stronger_label_when_the_grounded_answer_is_not_answered(ctx, kb):
    ctx.llm.queue(status="partial", answer="Part of it [E1].")
    ctx.llm.responses.append("A general explanation.")
    partial = answer_question(ctx, kb, QUESTION, explain=True)
    assert partial.explanation_label == LABEL_UNVERIFIED
    assert "may differ from ICAI's answer, verify before relying on it" in LABEL_UNVERIFIED

    # Not enough evidence (gate 1, no grounded call): still explained, with the stronger label.
    ctx.llm.responses.append("Generally speaking, ...")
    calls = len(ctx.llm.calls)
    weak = answer_question(ctx, kb, "zzz qqq xxyyzz", explain=True)
    assert (weak.status, weak.answer) == ("insufficient", INSUFFICIENT_MESSAGE)
    assert (
        weak.explanation_label == LABEL_UNVERIFIED and weak.explanation == "Generally speaking, ..."
    )
    assert len(ctx.llm.calls) == calls + 1  # only the explanation call

    ctx.llm.queue(answer="Operating activities [E1].")
    ctx.llm.responses.append("A general explanation.")
    assert answer_question(ctx, kb, QUESTION, explain=True).explanation_label == LABEL


def test_a_failed_explanation_leaves_the_grounded_answer_untouched(ctx, kb, monkeypatch):
    ctx.llm.queue(answer="Operating activities [E1].")
    expected = answer_question(ctx, kb, QUESTION)

    real = ctx.llm.generate
    state = {"n": 0}

    def second_call_fails(messages, **kwargs):
        state["n"] += 1
        if state["n"] == 2:
            raise ProviderUnavailable("Gemini returned HTTP 503 (UNAVAILABLE) after one retry.")
        return real(messages, **kwargs)

    monkeypatch.setattr(ctx.llm, "generate", second_call_fails)
    ctx.llm.queue(answer="Operating activities [E1].")
    result = answer_question(ctx, kb, QUESTION, explain=True)
    assert grounded(result)[:4] == grounded(expected)[:4]
    assert result.explanation is None
    assert (
        "HTTP 503" in result.explanation_error and result.explanation_error not in result.warnings
    )


def test_no_explanation_call_when_the_grounded_answer_fails(ctx, kb):
    ctx.llm.responses.append("not json")
    calls = len(ctx.llm.calls)
    with pytest.raises(GenerationFailed):
        answer_question(ctx, kb, QUESTION, explain=True)
    assert len(ctx.llm.calls) == calls + 1


def test_cloud_without_opt_in_makes_no_call_at_all(ctx, kb):
    calls = len(ctx.llm.calls)
    with pytest.raises(CloudNotAllowed):
        answer_question(ctx, kb, QUESTION, provider="gemini", explain=True)
    assert len(ctx.llm.calls) == calls


def test_trace_records_the_request_but_not_the_text(ctx, kb):
    ctx.llm.queue(answer="Operating activities [E1].")
    ctx.llm.responses.append("SECRET-LOOKING TUTOR TEXT")
    result = answer_question(ctx, kb, QUESTION, explain=True)
    with ctx.db() as conn:
        row = conn.execute("SELECT * FROM query_traces WHERE id = ?", (result.trace_id,)).fetchone()
    info = json.loads(row["retrieval"])["explanation"]
    assert info["requested"] is True and info["ok"] is True
    assert "SECRET-LOOKING" not in json.dumps(dict(row))


def test_api_explain_flag(ctx, kb):
    with TestClient(create_app(ctx)) as client:
        ctx.llm.queue(answer="Operating activities [E1].")
        calls = len(ctx.llm.calls)
        plain = client.post(f"/kbs/{kb['id']}/query", json={"question": QUESTION}).json()
        assert plain["explanation"] is None and len(ctx.llm.calls) == calls + 1  # default off
        ctx.llm.queue(answer="Operating activities [E1].")
        ctx.llm.responses.append("A general explanation.")
        body = client.post(
            f"/kbs/{kb['id']}/query", json={"question": QUESTION, "explain": True}
        ).json()
        assert body["explanation"] == "A general explanation."
        assert body["explanation_label"] == LABEL
        assert body["answer"] == plain["answer"] and body["status"] == plain["status"]
