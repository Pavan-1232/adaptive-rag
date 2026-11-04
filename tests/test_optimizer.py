"""C5, C6, the profiler, sampling, in-memory scoring, the selection rule, and cap enforcement."""

import numpy as np
import pytest

from adaptive_rag.chunking import chunk_table_aware, count_tokens, find_tables
from adaptive_rag.chunking.semantic import breakpoints, chunk_semantic
from adaptive_rag.chunking.structure import MIN_SECTION_TOKENS, chunk_structure
from adaptive_rag.loaders import ExtractedDocument, Section, Unit
from adaptive_rag.optimizer.candidates import BY_ID
from adaptive_rag.optimizer.embcache import CachedEmbeddings
from adaptive_rag.optimizer.optimize import Caps, optimize_document
from adaptive_rag.optimizer.profile import profile_document
from adaptive_rag.optimizer.sampling import (
    FULL_DOCUMENT_TOKENS,
    SAMPLE_CAP_TOKENS,
    question_plan,
    sample_regions,
)
from adaptive_rag.optimizer.scoring import DocumentChunks, InMemoryIndex
from adaptive_rag.optimizer.selection import select
from fakes import FakeEmbeddings, QuestionLLM


def make_doc(text: str, sections=()) -> ExtractedDocument:
    return ExtractedDocument(text, "page", [Unit(1, 0, len(text))], list(sections))


def paragraphs(count: int, words: int = 60, topic: str = "revenue") -> str:
    return "\n\n".join(
        f"Section {i} paragraph about {topic}. "
        + " ".join(f"{topic}{i % 7} word{j}." for j in range(words))
        for i in range(count)
    )


TABLE = "\n".join(
    ["Consolidated Statements of Operations", "(in millions)", "2024 2023 2022"]
    + [f"Line item {name} {i},480 {i},509 {i},210" for i, name in enumerate("abcdefgh", 1)]
)


def sectioned(count=8, words=80):
    parts, sections, position = [], [], 0
    for i in range(count):
        body = f"Heading {i}\n" + " ".join(f"topic{i} detail{j}." for j in range(words))
        sections.append(Section(f"Heading {i}", position, position + len(body)))
        parts.append(body)
        position += len(body) + 2
    text = "\n\n".join(parts)
    fixed = [Section(s.heading, s.start, min(s.end, len(text))) for s in sections]
    return make_doc(text, fixed)


# ---------------------------------------------------------------- C5


def test_structure_chunks_never_cross_a_section_boundary():
    doc = sectioned()
    chunks = chunk_structure(doc, 128, 10)
    bounds = [s.start for s in doc.sections[1:]]
    for chunk in chunks:
        assert doc.text[chunk.start : chunk.end] == chunk.text
        assert chunk.token_count <= 128
        assert not any(chunk.start < b < chunk.end for b in bounds)


def test_structure_merges_tiny_sections_forward():
    text = "Title\nA\n\nIntro\n" + " ".join(f"word{i}." for i in range(200))
    tiny_end = text.index("Intro")
    doc = make_doc(text, [Section("Title", 0, tiny_end), Section("Intro", tiny_end, len(text))])
    assert count_tokens(text[:tiny_end]) < MIN_SECTION_TOKENS
    first = chunk_structure(doc, 512, 0)[0]
    assert first.start == 0 and first.end > tiny_end


# ---------------------------------------------------------------- C6


def test_breakpoints_fall_where_the_topic_shifts():
    a, b = np.array([1.0, 0.0]), np.array([0.0, 1.0])
    vectors = np.array([a] * 20 + [b] * 20)
    assert breakpoints(vectors) == [19]


def test_semantic_offsets_sizes_and_regions():
    text = paragraphs(10, topic="revenue") + "\n\n" + paragraphs(10, topic="climate")
    doc = make_doc(text)
    whole = chunk_semantic(doc, FakeEmbeddings(), size=128)
    for chunk in whole:
        assert doc.text[chunk.start : chunk.end] == chunk.text
        assert chunk.token_count <= 128
    region = (len(text) // 4, len(text) // 2)
    limited = chunk_semantic(doc, FakeEmbeddings(), size=128, regions=[region])
    assert limited and all(region[0] <= c.start and c.end <= region[1] for c in limited)


# ---------------------------------------------------------------- profile and sampling


def test_profile_flags_reliable_headings_and_tables():
    good = profile_document(sectioned(), "pdf")
    assert good.headings_reliable and not good.has_tables
    few = profile_document(make_doc(paragraphs(5), [Section("Only", 0, 10)]), "pdf")
    assert not few.headings_reliable
    tabled = profile_document(make_doc(paragraphs(3) + "\n\n" + TABLE), "pdf")
    assert tabled.has_tables and tabled.table_count == 1 and 0 < tabled.table_share < 1


def test_short_documents_are_sampled_in_full():
    doc = make_doc(paragraphs(10))
    assert count_tokens(doc.text) <= FULL_DOCUMENT_TOKENS
    assert sample_regions(doc) == [(0, len(doc.text))]


def test_long_documents_are_sampled_to_a_quarter_capped_and_tables_kept_whole():
    body = [paragraphs(4, words=200, topic=f"t{i}") for i in range(60)]
    body.insert(30, TABLE)
    doc = make_doc("\n\n".join(body))
    total = count_tokens(doc.text)
    regions = sample_regions(doc)
    sampled = sum(count_tokens(doc.text[s:e]) for s, e in regions)
    assert total > FULL_DOCUMENT_TOKENS
    assert sampled <= min(SAMPLE_CAP_TOKENS, 0.25 * total) * 1.1  # line snapping adds a little
    for table in find_tables(doc.text):
        for start, end in regions:
            assert not (table.start < start < table.end or table.start < end < table.end)


def test_question_plan_includes_table_questions_when_tables_matter():
    doc = make_doc(paragraphs(3, words=20) + "\n\n" + TABLE + "\n\n" + paragraphs(3, words=20))
    plan = question_plan(doc, [(0, len(doc.text))], 40)
    assert len(plan) == 40
    assert sum(kind == "table" for *_, kind in plan) >= 3
    no_tables = question_plan(make_doc(paragraphs(20)), [(0, 10_000)], 12)
    assert all(kind != "table" for *_, kind in no_tables)


# ---------------------------------------------------------------- scoring and selection


def test_in_memory_index_charges_table_context():
    rows = "\n".join(f"Segment item {i} revenue {i},101 {i},202" for i in range(150))
    doc = make_doc("Table 1. Segments\n(in millions)\n2024 2023\n" + rows)
    chunks = chunk_table_aware(doc, 256, 0)
    index = InMemoryIndex([DocumentChunks("d.pdf", doc, chunks)], FakeEmbeddings())
    assert [r.token_count for r in index.ranked] == [c.evidence_tokens for c in chunks]
    assert any(c.context_tokens for c in chunks)


def test_selection_picks_a_clear_winner():
    scores = {"C1": [0.0] * 30, "C3": [1.0] * 30}
    winner, rankings = select(scores, {"C1": 100, "C3": 100})
    assert (
        winner == "C3" and not next(r for r in rankings if r.candidate_id == "C1").tied_with_leader
    )


def test_selection_tie_goes_to_the_simplest():
    leader = [1.0, 0.0] * 15
    close = [1.0, 0.0] * 14 + [0.0, 0.0]
    winner, _ = select({"C7": leader, "C1": close}, {"C7": 100, "C1": 100})
    assert winner == "C1"


def test_selection_tie_within_a_strategy_goes_to_smallest_storage():
    same = [1.0, 0.0] * 15
    winner, _ = select({"C2": same, "C4": same}, {"C2": 900, "C4": 500})
    assert winner == "C4"


# ---------------------------------------------------------------- caps


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class RecordingEmbeddings(FakeEmbeddings):
    def __init__(self, events):
        super().__init__()
        self.events = events

    def embed_documents(self, texts, titles):
        self.events.append("embed")
        return super().embed_documents(texts, titles)


def long_lines_doc():
    lines = [
        f"Line {i} reports that regional sales of widgets changed by a stated amount."
        for i in range(1500)
    ]
    return make_doc("\n".join(lines) + "\n\n" + TABLE)


def test_question_and_call_caps_and_llm_unloaded_before_embedding():
    llm = QuestionLLM()
    embedder = RecordingEmbeddings(llm.events)
    result = optimize_document(
        long_lines_doc(), "d.pdf", "pdf", embedder, llm, Caps(max_questions=12, max_llm_calls=15)
    )
    assert result.questions_selection + result.questions_confirmation <= 12
    assert result.llm_calls <= 15
    assert llm.events.index("unload") < llm.events.index("embed")
    assert "generate" not in llm.events[llm.events.index("unload") :]


def test_time_cap_stops_generation_and_skips_semantic_first():
    clock = Clock()
    llm = QuestionLLM(clock, seconds_per_call=100.0)
    caps = Caps(time_budget_s=1000.0, generation_share=0.5, min_selection_questions=1)

    class SlowEmbeddings(FakeEmbeddings):
        def embed_documents(self, texts, titles):
            clock.now += 120.0
            return super().embed_documents(texts, titles)

    result = optimize_document(
        long_lines_doc(), "d.pdf", "pdf", SlowEmbeddings(), llm, caps, clock=clock
    )
    assert llm.calls <= 6  # 500 s of generation at 100 s per call
    assert any("question generation" in s for s in result.stopped_early)
    statuses = {c.id: c.status for c in result.candidates}
    assert statuses["C6"].startswith("skipped: time cap")
    assert result.candidates[-1].id == "C6"  # semantic is tried last


def test_too_few_questions_keeps_the_control():
    result = optimize_document(
        long_lines_doc(),
        "d.pdf",
        "pdf",
        FakeEmbeddings(),
        QuestionLLM(),
        Caps(max_questions=5, max_llm_calls=5),
    )
    assert result.winner == "C1" and "kept the control" in result.winner_reason


def test_candidate_cap_and_applicability():
    caps = Caps(max_questions=12, max_llm_calls=12, max_candidates=2, min_selection_questions=1)
    result = optimize_document(
        long_lines_doc(), "d.pdf", "pdf", FakeEmbeddings(), QuestionLLM(), caps
    )
    statuses = {c.id: c.status for c in result.candidates}
    assert sum(s == "scored" for s in statuses.values()) == 2
    assert statuses["C5"] == "not applicable"  # no reliable headings
    assert BY_ID[result.winner].id in ("C1", "C2")


# ---------------------------------------------------------------- embedding cache


def test_embedding_cache_avoids_re_embedding(tmp_path):
    inner = RecordingEmbeddings([])
    cache = CachedEmbeddings(inner, tmp_path / "cache.sqlite")
    first = cache.embed_documents(["alpha beta", "gamma"], ["t", "t"])
    second = cache.embed_documents(["alpha beta", "gamma"], ["t", "t"])
    assert inner.events == ["embed"]
    assert np.allclose(first, second, atol=1e-6)
    cache.embed_documents(["alpha beta"], ["other title"])  # title is part of the key
    assert inner.events == ["embed", "embed"]


def test_unknown_candidate_strategy_rejected():
    with pytest.raises(KeyError):
        BY_ID["C9"]


def test_selection_questions_come_before_confirmation():
    from adaptive_rag.optimizer.optimize import _split

    for total, confirm in ((40, 10), (14, 3), (3, 0)):
        questions = list(range(total))
        selection, confirmation = _split(questions, 10)
        assert len(confirmation) == confirm and len(selection) == total - confirm
        assert sorted(selection + confirmation) == questions
