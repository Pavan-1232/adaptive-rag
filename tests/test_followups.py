"""Follow-up questions (answering/followup.py): rules, search text, KB boundaries, traces, API."""

import pytest
from fastapi.testclient import TestClient

from adaptive_rag.answering import answer_question
from adaptive_rag.answering.followup import SEPARATOR, is_follow_up
from adaptive_rag.api import create_app
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base

UNIT = (
    "TEST YOUR KNOWLEDGE\nMultiple Choice Questions\n"
    "1. Vega Ltd. paid income tax of 12,000 on its operating profit. Under which activity is it "
    "shown in the cash flow statement?\n(a) Operating activities\n(b) Investing activities\n"
    "(c) Financing activities\n(d) Not shown\n\n"
)
FIRST = "Can you give me a solution to question 1, the Vega Ltd income tax cash flow question?"


@pytest.mark.parametrize(
    "question",
    [
        "what is the answer",
        "What is the answer?",
        "explain it simply",
        "Why?",
        "Can you explain that in more detail please",
        "what is the correct option",
        "and question 2?",
        "What about part (b)?",
    ],
)
def test_follow_ups_are_detected(question):
    assert is_follow_up(question)


@pytest.mark.parametrize(
    "question",
    [
        "What is AS 3?",
        "What is prudence?",
        "How much did revenue grow in 2024?",
        FIRST,
        "",
    ],
)
def test_questions_with_their_own_subject_stand_alone(question):
    assert not is_follow_up(question)


def make_kb(ctx, tmp_path, name, text):
    kb = create_knowledge_base(ctx, name)
    path = tmp_path / f"{name}.txt"
    path.write_text(text)
    _, job_id, _ = register_upload(ctx, kb, path, f"{name}.txt")
    run_ingest_job(ctx, job_id)
    return kb


def trace(ctx, trace_id):
    with ctx.db() as conn:
        return conn.execute("SELECT * FROM query_traces WHERE id = ?", (trace_id,)).fetchone()


def used_chunks(ctx, trace_id):
    import json

    return [r["chunk_id"] for r in json.loads(trace(ctx, trace_id)["retrieved"]) if r["used"]]


def test_follow_up_searches_the_earlier_question_and_tells_the_model(ctx, tmp_path):
    kb = make_kb(ctx, tmp_path, "unit", UNIT)
    ctx.llm.queue(answer="Question 1 is about income tax [E1].")
    first = answer_question(ctx, kb, FIRST)
    assert first.searched_question == FIRST

    ctx.llm.queue(answer="(a) Operating activities [E1].")
    second = answer_question(ctx, kb, "what is the answer", previous_trace_id=first.trace_id)
    assert second.searched_question == FIRST + SEPARATOR + "what is the answer"
    assert used_chunks(ctx, second.trace_id) == used_chunks(ctx, first.trace_id)
    prompt = ctx.llm.calls[-1][1]["content"]
    assert "earlier question in this chat was" in prompt and FIRST in prompt
    assert prompt.rstrip().endswith('Question: "what is the answer"')

    row = trace(ctx, second.trace_id)
    assert row["question"] == "what is the answer"
    assert row["searched_question"] == second.searched_question
    assert row["base_question"] == FIRST and row["follows_trace_id"] == first.trace_id


def test_a_chain_of_follow_ups_builds_on_the_first_question(ctx, tmp_path):
    kb = make_kb(ctx, tmp_path, "unit", UNIT)
    ctx.llm.queue()
    first = answer_question(ctx, kb, FIRST)
    ctx.llm.queue()
    second = answer_question(ctx, kb, "what is the answer", previous_trace_id=first.trace_id)
    ctx.llm.queue()
    third = answer_question(ctx, kb, "explain it simply", previous_trace_id=second.trace_id)
    assert third.searched_question == FIRST + SEPARATOR + "explain it simply"  # no pile-up
    assert trace(ctx, third.trace_id)["base_question"] == FIRST


def test_a_new_question_after_a_chain_stands_alone(ctx, tmp_path):
    kb = make_kb(ctx, tmp_path, "unit", UNIT)
    ctx.llm.queue()
    first = answer_question(ctx, kb, FIRST)
    ctx.llm.queue()
    new = answer_question(
        ctx, kb, "Under which activity is income tax shown?", previous_trace_id=first.trace_id
    )
    assert new.searched_question == "Under which activity is income tax shown?"
    row = trace(ctx, new.trace_id)
    assert row["follows_trace_id"] is None and row["base_question"] == row["question"]


def test_a_previous_turn_from_another_knowledge_base_is_never_used(ctx, tmp_path):
    vega = make_kb(ctx, tmp_path, "vega", UNIT)
    other = make_kb(ctx, tmp_path, "other", "Orion Ltd. leases two warehouses in Pune.\n")
    ctx.llm.queue()
    first = answer_question(ctx, vega, FIRST)

    ctx.llm.queue(answer="Orion leases warehouses [E1].")
    calls_before = len(ctx.llm.calls)
    result = answer_question(ctx, other, "what is the answer", previous_trace_id=first.trace_id)
    assert result.searched_question == "what is the answer"
    assert any("another knowledge base" in w for w in result.warnings)
    with ctx.db() as conn:
        other_docs = {
            r[0] for r in conn.execute("SELECT id FROM documents WHERE kb_id = ?", (other["id"],))
        }
    assert {int(cid.split("-")[0]) for cid in used_chunks(ctx, result.trace_id)} <= other_docs
    # Nothing from the other knowledge base's chat reaches the model (if it's called at all).
    assert all(FIRST not in call[1]["content"] for call in ctx.llm.calls[calls_before:])


def test_an_unknown_previous_turn_means_standalone(ctx, tmp_path):
    kb = make_kb(ctx, tmp_path, "unit", UNIT)
    ctx.llm.queue()
    result = answer_question(ctx, kb, "what is the answer", previous_trace_id=99999)
    assert result.searched_question == "what is the answer"
    assert any("wasn't found" in w for w in result.warnings)


def test_api_accepts_previous_trace_id_and_returns_the_searched_question(ctx, tmp_path):
    kb = make_kb(ctx, tmp_path, "unit", UNIT)
    with TestClient(create_app(ctx)) as client:
        ctx.llm.queue()
        first = client.post(f"/kbs/{kb['id']}/query", json={"question": FIRST}).json()
        assert first["searched_question"] == FIRST
        ctx.llm.queue()
        second = client.post(
            f"/kbs/{kb['id']}/query",
            json={"question": "what is the answer", "previous_trace_id": first["trace_id"]},
        ).json()
        assert second["searched_question"].startswith(FIRST)
        bad = client.post(
            f"/kbs/{kb['id']}/query", json={"question": "why?", "previous_trace_id": 0}
        )
        assert bad.status_code == 422
