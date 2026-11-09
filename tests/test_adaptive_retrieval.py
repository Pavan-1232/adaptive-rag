"""Stage 5: query splitting, selection, neighbors, budget, and the unchanged baseline."""

import json
from dataclasses import replace

import pytest

from adaptive_rag.answering import answer_question
from adaptive_rag.answering.prompts import SYSTEM_PROMPT, TABLE_RULE, build_messages, has_table
from adaptive_rag.chunking.base import count_tokens
from adaptive_rag.ingest import delete_document, register_upload, run_ingest_job
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
from adaptive_rag.retrieval.adaptive import expand, merge_block, select, uncovered_parts
from adaptive_rag.retrieval.baseline import load_neighbor, ready_document_ids
from adaptive_rag.retrieval.keyword import keyword_search, match_query


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
    ],
)
def test_multi_part_questions_are_split(question, parts):
    plan = analyze(question)
    assert plan.kind == "multi_part"
    assert list(plan.parts) == parts


@pytest.mark.parametrize(
    ("question", "parts"),
    [
        ("Compare the old method with the new baseline.", ["The old method", "The new baseline"]),
        ("How does the 2024 outlook differ from 2023?", None),
        ("Tesla versus Ford on margins?", None),
    ],
)
def test_comparative_questions_are_typed_and_still_split(question, parts):
    plan = analyze(question)
    assert plan.kind == "comparative"
    if parts:
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

# Rule tests switch off the rules they don't test, so each is checked on its own.
OFF = {"gap_cutoff": False, "merge_spans": False, "doc_cap": None}
PARAMS = AdaptiveParams(budget=1000, floor=0.25, delta=None, min_chunks=1, **OFF)


def test_each_part_gets_its_best_chunk_before_filling_by_score():
    plan = analyze("What is alpha, and how does beta work?")
    full = [chunk("a1", 0.9), chunk("a2", 0.85), chunk("a3", 0.8), chunk("b1", 0.4)]
    part_a = [chunk("a1", 0.92), chunk("a2", 0.88)]
    part_b = [chunk("b1", 0.5), chunk("a3", 0.3)]
    params = AdaptiveParams(budget=300, floor=0.25, delta=None, min_chunks=1, **OFF)
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
    params = AdaptiveParams(budget=2500, floor=0.25, delta=None, max_chunks={"factual": 10}, **OFF)
    chosen, stats = select(plan, [pool], params)
    assert sum(c.evidence_tokens for c in chosen) <= 2500
    assert len(chosen) == 4 and stats["stop_reason"] == "budget"


def test_floor_delta_and_max_stop_the_fill():
    plan = analyze("What is alpha?")
    pool = [chunk("c0", 0.9), chunk("c1", 0.85), chunk("c2", 0.6), chunk("c3", 0.2)]
    params = AdaptiveParams(budget=5000, floor=0.25, delta=0.1, min_chunks=1, **OFF)
    chosen, stats = select(plan, [pool], params)
    assert [c.chunk_id for c in chosen] == ["c0", "c1"] and stats["stop_reason"] == "delta"

    no_delta = AdaptiveParams(budget=5000, floor=0.25, delta=None, min_chunks=1, **OFF)
    chosen, stats = select(plan, [pool], no_delta)
    assert [c.chunk_id for c in chosen] == ["c0", "c1", "c2"] and stats["stop_reason"] == "floor"

    capped = AdaptiveParams(budget=5000, floor=0.0, delta=None, max_chunks={"factual": 2}, **OFF)
    chosen, stats = select(plan, [pool], capped)
    assert len(chosen) == 2 and stats["stop_reason"] == "max chunks"


def test_min_chunks_holds_off_the_delta_rule():
    plan = analyze("What is alpha?")
    pool = [chunk("c0", 0.9), chunk("c1", 0.5), chunk("c2", 0.45)]
    params = AdaptiveParams(budget=5000, floor=0.25, delta=0.1, min_chunks=3, **OFF)
    chosen, _ = select(plan, [pool], params)
    assert len(chosen) == 3


def test_near_identical_chunks_are_dropped_and_counted():
    plan = analyze("What is alpha?")
    row = "Research and development 4,540 3,969 3,075 total operating expenses"
    pool = [chunk("p40", 0.9, text=row), chunk("p52", 0.89, text=row), chunk("x", 0.8)]
    chosen, stats = select(plan, [pool], PARAMS)
    assert [c.chunk_id for c in chosen] == ["p40", "x"]
    assert stats["duplicates_dropped"] == 1 and stats["duplicate_tokens"] == 100

    keep = AdaptiveParams(budget=1000, floor=0.25, delta=None, dedupe=False, **OFF)
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
    params = AdaptiveParams(budget=1000, neighbors=True, expand_threshold=0.5, **OFF)
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
    params = AdaptiveParams(budget=400, neighbors=True, expand_threshold=0.5, **OFF)
    out = expand([h1, h2, weak], params, lookup)
    ids = [c.chunk_id for c in out]
    assert len(ids) == len(set(ids))
    assert "n19" not in ids  # weak hit isn't expanded
    assert sum(c.evidence_tokens for c in out) <= 400
    assert ids.count("n4") + ids.count("n7") == 1  # only one neighbor fits


def test_neighbors_off_returns_direct_hits_unchanged():
    direct = [chunk("x", 0.9, index=3), chunk("y", 0.8, index=9)]
    out = expand(direct, AdaptiveParams(neighbors=False, **OFF), neighbor_table())
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
    params = AdaptiveParams(budget=2500, floor=0.0, delta=None, max_chunks={"multi_part": 2}, **OFF)
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


# ---------------------------------------------------------------- audit additions (2026-11-05)


def test_gap_cutoff_stops_at_the_largest_drop_inside_the_range():
    plan = analyze("What is alpha?")
    pool = [chunk(f"c{i}", s) for i, s in enumerate([0.9, 0.88, 0.86, 0.6, 0.58])]
    gap = AdaptiveParams(budget=5000, delta=None, min_chunks=1, **{**OFF, "gap_cutoff": True})
    chosen, stats = select(plan, [pool], gap)
    assert [c.chunk_id for c in chosen] == ["c0", "c1", "c2"] and stats["stop_reason"] == "gap"

    # The range starts at min_chunks, so a drop before it can't cut.
    late = AdaptiveParams(budget=5000, delta=None, min_chunks=4, **{**OFF, "gap_cutoff": True})
    chosen, _ = select(plan, [pool], late)
    assert len(chosen) == 4

    chosen, stats = select(plan, [pool], AdaptiveParams(budget=5000, delta=None, **OFF))
    assert len(chosen) == 5 and stats["stop_reason"] == "pool exhausted"


def test_delta_off_never_stops_on_delta_and_stop_reasons_are_recorded():
    plan = analyze("What is alpha?")
    pool = [chunk("c0", 0.9), chunk("c1", 0.3), chunk("c2", 0.1)]
    params = AdaptiveParams(budget=5000, delta=None, min_chunks=1, **OFF)
    chosen, stats = select(plan, [pool], params)
    # 0.3 is far below 0.9 - any delta, but delta is off: only the floor stops the fill.
    assert [c.chunk_id for c in chosen] == ["c0", "c1"] and stats["stop_reason"] == "floor"

    on = AdaptiveParams(budget=5000, delta=0.2, min_chunks=1, **OFF)
    assert select(plan, [pool], on)[1]["stop_reason"] == "delta"


def text_chunk(cid, doc_text, start, end, index, score=0.8, doc=1, source="direct"):
    text = doc_text[start:end]
    return RetrievedChunk(
        chunk_id=cid,
        document_id=doc,
        filename=f"d{doc}.pdf",
        chunk_index=index,
        text=text,
        token_count=count_tokens(text),
        score=score,
        locator_kind="page",
        locator_start=index + 1,
        locator_end=index + 1,
        section_heading=None,
        source=source,
        start_char=start,
        end_char=end,
    )


DOC = " ".join(f"word{i}" for i in range(400))


def test_overlapping_chunks_merge_into_one_block_and_save_budget():
    a = text_chunk("a", DOC, 0, 600, 0, 0.9)
    b = text_chunk("b", DOC, 500, 1100, 1, 0.8)  # 100 characters shared with a
    c = text_chunk("c", DOC, 1500, 2100, 5, 0.7, doc=2)
    block = merge_block([a, b])
    assert block.text == DOC[0:1100] and block.members == (a, b)
    assert block.evidence_tokens < a.evidence_tokens + b.evidence_tokens
    assert (block.locator_start, block.locator_end, block.score) == (1, 2, 0.9)

    plan = analyze("What is alpha?")
    budget = a.evidence_tokens + b.evidence_tokens + c.evidence_tokens - 5
    merged = AdaptiveParams(budget=budget, delta=None, min_chunks=1, **{**OFF, "merge_spans": True})
    chosen, _ = select(plan, [[a, b, c]], merged)
    assert len(chosen) == 3  # fits only because the overlap is charged once
    plain = AdaptiveParams(budget=budget, delta=None, min_chunks=1, **OFF)
    assert len(select(plan, [[a, b, c]], plain)[0]) == 2

    out = expand(chosen, merged, neighbor_table())
    assert [len(x.pieces) for x in out] == [2, 1]
    assert sum(x.evidence_tokens for x in out) <= budget


def test_neighbor_blocks_merge_and_are_ordered_by_best_direct_score():
    x = chunk("x", 0.6, doc=1, index=10)
    z = chunk("z", 0.55, doc=1, index=12)
    y = chunk("y", 0.9, doc=2, index=3)
    lookup = neighbor_table(chunk("n11", 0, doc=1, index=11), chunk("n4", 0, doc=2, index=4))
    params = AdaptiveParams(
        budget=5000, neighbors=True, expand_threshold=0.5, **{**OFF, "merge_spans": True}
    )
    out = expand([x, z, y], params, lookup)
    assert [[p.chunk_id for p in b.pieces] for b in out] == [["y", "n4"], ["x", "n11", "z"]]
    assert [p.source for p in out[1].pieces] == ["direct", "expansion", "direct"]
    assert out[1].score == 0.6 and out[1].source == "direct"


def test_neighbor_reserve_holds_back_budget_for_neighbors():
    plan = analyze("What is alpha?")
    pool = [chunk(f"c{i}", 0.9 - i * 0.01, index=i * 10) for i in range(10)]
    many = {"factual": 10}
    reserve = AdaptiveParams(
        budget=1000, delta=None, max_chunks=many, neighbors=True, neighbor_reserve=0.3, **OFF
    )
    assert len(select(plan, [pool], reserve)[0]) == 7
    no_reserve = AdaptiveParams(
        budget=1000, delta=None, max_chunks=many, neighbors=True, neighbor_reserve=0.0, **OFF
    )
    assert len(select(plan, [pool], no_reserve)[0]) == 10


def test_document_cap_applies_to_comparative_questions_and_is_soft():
    one = [chunk(f"a{i}", 0.9 - i * 0.01, doc=1, index=i * 10) for i in range(4)]
    two = [chunk("b0", 0.5, doc=2), chunk("b1", 0.49, doc=2, index=10)]
    cap = {**OFF, "doc_cap": 2}
    params = AdaptiveParams(budget=5000, delta=None, max_chunks={"comparative": 4}, **cap)
    comparative = analyze("How does alpha differ from beta?")
    chosen, _ = select(comparative, [one + two], params)
    assert [c.chunk_id for c in chosen] == ["a0", "a1", "b0", "b1"]

    # Soft: with only one other chunk available, the capped document fills the room.
    chosen, stats = select(comparative, [one + two[:1]], params)
    assert [c.chunk_id for c in chosen] == ["a0", "a1", "b0", "a2"] and stats["capped"] == 1

    factual = AdaptiveParams(budget=5000, delta=None, max_chunks={"factual": 4}, **cap)
    chosen, _ = select(analyze("What is alpha?"), [one + two], factual)
    assert [c.chunk_id for c in chosen] == ["a0", "a1", "a2", "a3"]


def test_a_part_whose_best_chunk_is_dropped_for_budget_is_uncovered():
    plan = analyze("What is the alpha rate, and how does beta work?")
    assert len(plan.parts) == 2
    full = [chunk("a1", 0.9, tokens=300), chunk("b1", 0.6, tokens=600)]
    part_a = [chunk("a1", 0.92, tokens=300)]
    part_b = [chunk("b1", 0.7, tokens=600), chunk("junk", 0.1)]
    params = AdaptiveParams(budget=500, delta=None, min_chunks=1, **OFF)
    pools = [full, part_a, part_b]
    chosen, _ = select(plan, pools, params)
    assert [c.chunk_id for c in chosen] == ["a1"]  # b1 doesn't fit; junk is below the floor
    # Search found b1 above the floor, but it wasn't sent, so part b is uncovered.
    assert uncovered_parts(plan, pools, chosen, 0.25) == ["How does beta work?"]

    roomy = AdaptiveParams(budget=1000, delta=None, min_chunks=1, **OFF)
    assert uncovered_parts(plan, pools, select(plan, pools, roomy)[0], 0.25) == []


def test_table_rule_is_applied_only_when_evidence_holds_a_table(ctx, kb, tmp_path):
    rows = "\n".join(
        f"{label} $ {a:,} $ {b:,}"
        for label, a, b in [
            ("Automotive sales", 72480, 67210),
            ("Energy generation", 10086, 6035),
            ("Services and other", 10534, 8319),
        ]
    )
    assert has_table([chunk("t", 0.9, text="Revenues\n" + rows)])
    assert not has_table([chunk("p", 0.9, text="Revenue grew 3% in 2024 to $97 billion.")])

    add(ctx, kb, tmp_path, "prose.txt", "Cats purr and chase mice around the barn.")
    ctx.settings.retrieval = "adaptive"
    ctx.settings.table_prompt = True
    ctx.llm.queue()
    answer_question(ctx, kb, "Why do cats purr?")
    assert TABLE_RULE not in ctx.llm.calls[-1][0]["content"]

    add(ctx, kb, tmp_path, "table.txt", "Revenues by segment\n" + rows)
    ctx.llm.queue()
    answer_question(ctx, kb, "What were automotive sales revenues?")
    assert TABLE_RULE in ctx.llm.calls[-1][0]["content"]


def test_neighbors_never_cross_documents_through_the_database(ctx, kb, tmp_path):
    ctx.settings.chunk_size_tokens = 20
    ctx.settings.chunk_overlap_tokens = 5
    first = add(ctx, kb, tmp_path, "a.txt", " ".join(f"alpha{i}" for i in range(60)))
    second = add(ctx, kb, tmp_path, "b.txt", " ".join(f"beta{i}" for i in range(200)))
    with ctx.db() as conn:
        last = conn.execute(
            "SELECT MAX(chunk_index) FROM chunks WHERE document_id = ?", (first,)
        ).fetchone()[0]
        assert conn.execute(
            "SELECT 1 FROM chunks WHERE document_id = ? AND chunk_index = ?", (second, last + 1)
        ).fetchone()
    assert load_neighbor(ctx, first, last + 1, 0.9) is None  # exists only in the other document

    params = AdaptiveParams(
        budget=4000, floor=-1, delta=None, neighbors=True, expand_threshold=-1, **OFF
    )
    result = retrieve_adaptive(ctx, kb, f"alpha{55} alpha{59}", params)
    pieces = [p for c in result.chunks for p in c.pieces]
    direct = {(p.document_id, p.chunk_index) for p in pieces if p.source == "direct"}
    expansions = [p for p in pieces if p.source == "expansion"]
    assert expansions
    for p in expansions:
        assert (p.document_id, p.chunk_index - 1) in direct or (
            p.document_id,
            p.chunk_index + 1,
        ) in direct


def test_stop_reason_reaches_the_trace_info(ctx, kb, tmp_path):
    add(ctx, kb, tmp_path, "cats.txt", "Cats purr and chase mice around the barn.")
    ctx.settings.retrieval = "adaptive"
    ctx.settings.adaptive_delta = None
    evidence = retrieve_evidence(ctx, kb, "Why do cats purr?")
    params = AdaptiveParams.from_settings(ctx.settings, kb["embedding_model"])
    assert params.delta is None
    expected = retrieve_adaptive(ctx, kb, "Why do cats purr?", params).stop_reason
    assert evidence.info["stop_reason"] == expected != "delta"


# ---------------------------------------------------------------- hybrid keyword search


def test_match_query_quotes_words_so_user_text_is_never_fts_syntax():
    assert (
        match_query('NEAR("alpha" OR beta*) AND -gamma') == '"near" OR "alpha" OR "beta" OR "gamma"'
    )
    assert match_query("the of and") is None


def test_keyword_index_follows_ingest_and_delete(ctx, kb, tmp_path):
    lathrop = add(ctx, kb, tmp_path, "plant.txt", "The Lathrop facility builds Megapacks.")
    add(ctx, kb, tmp_path, "other.txt", "Revenue from services grew in the year.")
    hits = keyword_search(ctx, "Where is Lathrop?", 5, ready_document_ids(ctx, kb))
    with ctx.db() as conn:
        owner = conn.execute(
            "SELECT document_id FROM chunks WHERE id = ?", (hits[0][0],)
        ).fetchone()[0]
    assert owner == lathrop and hits[0][1] == 1.0
    delete_document(ctx, lathrop)
    assert keyword_search(ctx, "Lathrop", 5, ready_document_ids(ctx, kb)) == []
    with ctx.db() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
            == conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        )


def test_hybrid_ranks_keyword_hits_up_but_keeps_the_cosine_floor():
    plan = analyze("What is alpha?")
    dense = chunk("dense", 0.62)
    row = replace(chunk("row", 0.55), keyword=1.0)
    weak = replace(chunk("weak", 0.1), keyword=1.0)
    hybrid = AdaptiveParams(
        budget=5000, delta=None, min_chunks=1, hybrid=True, keyword_weight=0.1, **OFF
    )
    chosen, _ = select(plan, [[dense, row, weak]], hybrid)
    assert [c.chunk_id for c in chosen] == ["row", "dense"]  # weak stays below the floor
    vector_only = AdaptiveParams(budget=5000, delta=None, min_chunks=1, **OFF)
    assert [c.chunk_id for c in select(plan, [[dense, row, weak]], vector_only)[0]] == [
        "dense",
        "row",
    ]


def test_hybrid_pool_scores_keyword_only_hits_by_cosine(ctx, kb, tmp_path):
    add(ctx, kb, tmp_path, "plant.txt", "The Lathrop facility builds Megapacks.")
    params = AdaptiveParams(hybrid=True, pool_size=1, floor=-1, **OFF)
    result = retrieve_adaptive(ctx, kb, "Lathrop", params)
    assert result.candidates and all(-1 <= c.score <= 1 for c in result.candidates)
    assert result.tokens > 0


# ------------------------------------------- keyword query "phrases" and RRF fusion (2026-11-09)


def test_phrase_query_keeps_identifiers_and_stays_safe():
    query = match_query("What does Paper 4 May 2025 Q.5 ask in Chapter 1?", "phrases")
    for term in ('"may 2025"', '"q 5"', '"chapter 1"', '"5"', '"1"'):
        assert term in query.split(" OR ")
    assert '"as 20"' in match_query("Which pages cover AS 20?", "phrases")
    assert '"as"' not in match_query("Which pages cover as much?", "phrases").split(" OR ")
    # Still only quoted \w+ words: user text can't become FTS5 syntax.
    assert match_query('NEAR("alpha" OR beta*) AND -gamma', "phrases") == (
        '"near alpha" OR "near" OR "alpha" OR "beta" OR "gamma"'
    )
    assert match_query("the of and", "phrases") is None
    assert match_query("What is alpha?") == '"alpha"'  # "words" is unchanged


def test_rrf_puts_a_strong_keyword_hit_in_past_the_floor():
    plan = analyze("What is Paper 4 May 2025 Q.5?")
    dense = [chunk(f"d{i}", 0.6 - i * 0.01) for i in range(6)]
    dense[0] = replace(dense[0], keyword=0.5)  # keyword rank 2
    exact = replace(chunk("exact", 0.1), keyword=1.0)  # keyword rank 1; far below the floor
    noise = replace(chunk("noise", 0.1), keyword=0.2)  # keyword rank 3: not strong
    pool = [*dense, exact, noise]
    rrf = AdaptiveParams(budget=5000, delta=None, min_chunks=1, hybrid=True, fusion="rrf", **OFF)
    chosen = [c.chunk_id for c in select(plan, [pool], rrf)[0]]
    assert chosen[:2] == ["d0", "exact"]  # both strong hits first, by fused rank
    assert "noise" not in chosen and len(chosen) == 5  # rank 3 isn't strong; the limit holds
    weighted = AdaptiveParams(budget=5000, delta=None, min_chunks=1, hybrid=True, **OFF)
    assert "exact" not in [c.chunk_id for c in select(plan, [pool], weighted)[0]]


def test_rrf_respects_the_budget_and_off_means_unchanged():
    plan = analyze("What is alpha?")
    exact = replace(chunk("exact", 0.1, tokens=900), keyword=1.0)
    rrf = AdaptiveParams(budget=500, delta=None, min_chunks=1, hybrid=True, fusion="rrf", **OFF)
    assert "exact" not in [c.chunk_id for c in select(plan, [[chunk("a", 0.6), exact]], rrf)[0]]
    no_hybrid = AdaptiveParams(budget=5000, delta=None, min_chunks=1, fusion="rrf", **OFF)
    assert [c.chunk_id for c in select(plan, [[chunk("a", 0.6), exact]], no_hybrid)[0]] == ["a"]
