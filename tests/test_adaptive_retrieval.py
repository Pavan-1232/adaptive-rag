"""Stage 5: query splitting, selection, neighbors, budget, and the unchanged baseline."""

import json

import pytest

from adaptive_rag.answering import answer_question
from adaptive_rag.answering.prompts import SYSTEM_PROMPT, TABLE_RULE, build_messages
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.retrieval import (
    AdaptiveParams,
    RetrievedChunk,
    analyze,
    fit_to_budget,
    retrieve_adaptive,
    retrieve_baseline,
    retrieve_evidence,
)
from adaptive_rag.retrieval.adaptive import expand, select


def chunk(cid, score, doc=1, index=0, tokens=100, text=None, heading=None, source="direct"):
    return RetrievedChunk(
        chunk_id=cid,
        document_id=doc,
        filename=f"d{doc}.pdf",
        chunk_index=index,
        text=text if text is not None else f"unique text for chunk {cid} " * 3,
        token_count=tokens,
        score=score,
        locator_kind="page",
        locator_start=1,
        locator_end=1,
        section_heading=heading,
        source=source,
    )


# ---------------------------------------------------------------- query analysis


@pytest.mark.parametrize(
    ("question", "parts"),
    [
        (
            "What does the company make in Buffalo, and how long does it have to spend $5B?",
            ["What does the company make in Buffalo", "How long does it have to spend $5B?"],
        ),
        (
            "How many cars were delivered? Did revenue grow or shrink?",
            ["How many cars were delivered?", "Did revenue grow or shrink?"],
        ),
        ("Compare the old method with the new baseline.", ["The old method", "The new baseline"]),
    ],
)
def test_multi_part_questions_are_split(question, parts):
    plan = analyze(question)
    assert plan.kind == "multi_part"
    assert list(plan.parts) == parts


@pytest.mark.parametrize(
    "question",
    [
        "In the December 2024 projections, what median unemployment rate was expected?",
        "According to the MANAGE function, who should be told about incidents?",
        "What is the purpose of the framework?",
    ],
)
def test_lead_ins_and_single_questions_are_not_split(question):
    assert analyze(question).parts == (question,)


def test_splitting_can_be_turned_off():
    plan = analyze("What is X, and how does Y work?", split=False)
    assert plan.parts == ("What is X, and how does Y work?",)
    assert plan.kind != "multi_part"


# ---------------------------------------------------------------- selection

PARAMS = AdaptiveParams(budget=1000, floor=0.25, delta=None, min_chunks=1)


def test_each_part_gets_its_best_chunk_before_filling_by_score():
    plan = analyze("What is alpha, and how does beta work?")
    full = [chunk("a1", 0.9), chunk("a2", 0.85), chunk("a3", 0.8), chunk("b1", 0.4)]
    part_a = [chunk("a1", 0.92), chunk("a2", 0.88)]
    part_b = [chunk("b1", 0.5), chunk("a3", 0.3)]
    params = AdaptiveParams(budget=300, floor=0.25, delta=None, min_chunks=1)
    chosen, _ = select(plan, [full, part_a, part_b], params)
    # Plain top-3 by score would be a1, a2, a3 and miss part b entirely.
    assert [c.chunk_id for c in chosen] == ["a1", "b1", "a2"]


def test_a_part_below_the_floor_gets_no_forced_pick():
    plan = analyze("What is alpha, and how does beta work?")
    full = [chunk("a1", 0.9), chunk("a2", 0.85)]
    part_b = [chunk("junk", 0.1)]
    chosen, _ = select(plan, [full, [chunk("a1", 0.9)], part_b], PARAMS)
    assert "junk" not in [c.chunk_id for c in chosen]


def test_budget_is_never_exceeded():
    plan = analyze("What is alpha?")
    pool = [chunk(f"c{i}", 0.9 - i * 0.01, tokens=512) for i in range(10)]
    params = AdaptiveParams(budget=2500, floor=0.25, delta=None, max_chunks={"factual": 10})
    chosen, stats = select(plan, [pool], params)
    assert sum(c.evidence_tokens for c in chosen) <= 2500
    assert len(chosen) == 4 and stats["stop_reason"] == "budget"


def test_floor_delta_and_max_stop_the_fill():
    plan = analyze("What is alpha?")
    pool = [chunk("c0", 0.9), chunk("c1", 0.85), chunk("c2", 0.6), chunk("c3", 0.2)]
    params = AdaptiveParams(budget=5000, floor=0.25, delta=0.1, min_chunks=1)
    chosen, stats = select(plan, [pool], params)
    assert [c.chunk_id for c in chosen] == ["c0", "c1"] and stats["stop_reason"] == "delta"

    no_delta = AdaptiveParams(budget=5000, floor=0.25, delta=None, min_chunks=1)
    chosen, stats = select(plan, [pool], no_delta)
    assert [c.chunk_id for c in chosen] == ["c0", "c1", "c2"] and stats["stop_reason"] == "floor"

    capped = AdaptiveParams(budget=5000, floor=0.0, delta=None, max_chunks={"factual": 2})
    chosen, stats = select(plan, [pool], capped)
    assert len(chosen) == 2 and stats["stop_reason"] == "max chunks"


def test_min_chunks_holds_off_the_delta_rule():
    plan = analyze("What is alpha?")
    pool = [chunk("c0", 0.9), chunk("c1", 0.5), chunk("c2", 0.45)]
    params = AdaptiveParams(budget=5000, floor=0.25, delta=0.1, min_chunks=3)
    chosen, _ = select(plan, [pool], params)
    assert len(chosen) == 3


def test_near_identical_chunks_are_dropped_and_counted():
    plan = analyze("What is alpha?")
    row = "Research and development 4,540 3,969 3,075 total operating expenses"
    pool = [chunk("p40", 0.9, text=row), chunk("p52", 0.89, text=row), chunk("x", 0.8)]
    chosen, stats = select(plan, [pool], PARAMS)
    assert [c.chunk_id for c in chosen] == ["p40", "x"]
    assert stats["duplicates_dropped"] == 1 and stats["duplicate_tokens"] == 100

    keep = AdaptiveParams(budget=1000, floor=0.25, delta=None, dedupe=False)
    chosen, _ = select(plan, [pool], keep)
    assert len(chosen) == 3


def test_no_chunk_is_selected_twice():
    plan = analyze("What is alpha, and how does beta work?")
    shared = [chunk("s", 0.9), chunk("t", 0.8)]
    chosen, _ = select(plan, [shared, shared, shared], PARAMS)
    ids = [c.chunk_id for c in chosen]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- neighbors


def neighbor_table(*chunks):
    by_key = {(c.document_id, c.chunk_index): c for c in chunks}

    def lookup(document_id, index, score):
        found = by_key.get((document_id, index))
        if found is None:
            return None
        return RetrievedChunk(**{**found.__dict__, "score": score, "source": "expansion"})

    return lookup


def test_neighbors_stay_in_document_and_section_and_are_marked():
    hit = chunk("h", 0.8, doc=1, index=5, heading="Results")
    before = chunk("b", 0.0, doc=1, index=4, heading="Results")
    after = chunk("a", 0.0, doc=1, index=6, heading="Appendix")  # different section
    other_doc = chunk("o", 0.0, doc=2, index=6, heading="Results")
    lookup = neighbor_table(before, after, other_doc)
    params = AdaptiveParams(budget=1000, neighbors=True, expand_threshold=0.5)
    out = expand([hit], params, lookup)
    assert [c.chunk_id for c in out] == ["b", "h"]  # document order inside the block
    assert [c.source for c in out] == ["expansion", "direct"]


def test_neighbors_respect_budget_threshold_and_duplicates():
    h1 = chunk("h1", 0.8, index=5)
    h2 = chunk("h2", 0.7, index=6)  # already selected: not added again as h1's neighbor
    weak = chunk("w", 0.3, index=20)
    lookup = neighbor_table(
        chunk("n4", 0, index=4), chunk("n7", 0, index=7), chunk("n19", 0, index=19)
    )
    params = AdaptiveParams(budget=400, neighbors=True, expand_threshold=0.5)
    out = expand([h1, h2, weak], params, lookup)
    ids = [c.chunk_id for c in out]
    assert len(ids) == len(set(ids))
    assert "n19" not in ids  # weak hit isn't expanded
    assert sum(c.evidence_tokens for c in out) <= 400
    assert ids.count("n4") + ids.count("n7") == 1  # only one neighbor fits


def test_neighbors_off_returns_direct_hits_unchanged():
    direct = [chunk("x", 0.9, index=3), chunk("y", 0.8, index=9)]
    out = expand(direct, AdaptiveParams(neighbors=False), neighbor_table())
    assert out == direct


# ---------------------------------------------------------------- end to end, with fakes


def add(ctx, kb, tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    document, job_id, _ = register_upload(ctx, kb, path, name)
    run_ingest_job(ctx, job_id)
    return document["id"]


@pytest.fixture
def kb(ctx):
    return create_knowledge_base(ctx, "KB")


def test_adaptive_retrieval_covers_both_parts(ctx, kb, tmp_path):
    add(ctx, kb, tmp_path, "cats.txt", "Cats purr and chase mice around the barn.")
    add(ctx, kb, tmp_path, "dogs.txt", "Dogs bark loudly at the mail carrier.")
    add(ctx, kb, tmp_path, "fish.txt", "Goldfish swim in small glass bowls.")
    params = AdaptiveParams(budget=2500, floor=0.0, delta=None, max_chunks={"multi_part": 2})
    result = retrieve_adaptive(ctx, kb, "Why do cats purr, and why do dogs bark?", params)
    assert result.plan.kind == "multi_part"
    assert {c.filename for c in result.chunks} == {"cats.txt", "dogs.txt"}
    assert result.tokens <= 2500


def test_baseline_mode_is_unchanged(ctx, kb, tmp_path):
    """Regression guard for system A (decision 48): baseline evidence is exactly top_k under
    the hard maximum, and the prompt is byte-identical to Stage 4's when no switch is on."""
    for i in range(7):
        add(ctx, kb, tmp_path, f"d{i}.txt", f"Document {i} talks about revenue item {i}.")
    ctx.settings.retrieval = "baseline"
    evidence = retrieve_evidence(ctx, kb, "revenue item 3")
    expected = fit_to_budget(
        retrieve_baseline(ctx, kb, "revenue item 3", ctx.settings.top_k),
        ctx.settings.evidence_max_tokens,
    )
    assert evidence.used == expected and len(expected) == ctx.settings.top_k
    assert evidence.uncovered_parts == []
    messages = build_messages("q", expected)
    assert messages == build_messages("q", expected, [], False)
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "Search found no strong evidence" not in messages[1]["content"]


def test_defaults_keep_adaptive_and_table_prompt_off(settings):
    assert settings.retrieval == "baseline"
    assert settings.table_prompt is False


def test_prompt_switches(ctx):
    one = [chunk("x", 0.9)]
    with_rule = build_messages("q", one, None, True)
    assert with_rule[0]["content"] == SYSTEM_PROMPT + TABLE_RULE
    notice = build_messages("q", one, ["How large were total assets?"])[1]["content"]
    assert '"How large were total assets?"' in notice and "status partial" in notice


def test_adaptive_answer_writes_trace_and_still_refuses(ctx, kb, tmp_path):
    add(ctx, kb, tmp_path, "cats.txt", "Cats purr and chase mice around the barn.")
    ctx.settings.retrieval = "adaptive"
    ctx.llm.queue()
    result = answer_question(ctx, kb, "Why do cats purr?")
    assert result.status == "answered"
    with ctx.db() as conn:
        row = conn.execute(
            "SELECT retrieval FROM query_traces WHERE id = ?", (result.trace_id,)
        ).fetchone()
    info = json.loads(row["retrieval"])
    assert info["mode"] == "adaptive" and info["evidence_tokens"] <= info["budget"]

    # Gate 1 still applies: nothing above the evidence floor means no LLM call.
    ctx.settings.score_floors = {ctx.embedder.model: 0.99}
    calls = len(ctx.llm.calls)
    refused = answer_question(ctx, kb, "Quarterly tax law in Peru?")
    assert refused.status == "insufficient" and len(ctx.llm.calls) == calls
