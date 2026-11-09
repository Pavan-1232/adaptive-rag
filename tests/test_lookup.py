"""Stage 5b exact lookups (retrieval/lookup.py), via the real ingest pipeline on made-up PDFs."""

import json

import pytest

from adaptive_rag.answering import answer_question
from adaptive_rag.evaluation.runner import resume_conflicts
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.retrieval import retrieve_evidence
from adaptive_rag.structure import backfill
from documents import make_pdf

FILLER = "Notes on accounting practice and presentation of reports for students. " * 6
CONTENTS = [
    ("Book of Questions", 14),
    ("No. Chapter No. of Qs Page number", 9),
    ("1 Introduction to Standards 3 2 - 3", 9),
    ("2 Framework for Reports 2 4 - 4", 9),
    ("4.5 AS 20 - Earnings Per Share 4 5 - 6", 9),
    ("15 Branch Accounts 2 7 - 7", 9),
    ("Mix Revision case studies 6 8 - 9", 9),
]
PAGES = [
    CONTENTS,
    [
        ("Introduction to Standards", 12),
        ("Question index", 10),
        ("01 RTP - May 2025, Q.5", 9),
        ("02 ICAI SM - 1 Basics of Standards, TYK Q.1", 9),
        (FILLER, 9),
        ("01 RTP - May 2025, Q.5 Notebook Page No.", 9),
        ("Explain why a company discloses its significant accounting policies in one place.", 9),
    ],
    [("02 ICAI SM - 1 Basics of Standards, TYK Q.1 Notebook Page No.", 9), (FILLER, 9)],
    [("Framework for Reports", 12), (FILLER, 9)],
    [("AS 20 - Earnings Per Share", 12), (FILLER, 9)],
    [(FILLER, 9)],
    [("Branch Accounts", 12), (FILLER, 9)],
    [("Revision case studies", 12), (FILLER, 9)],
    [(FILLER, 9)],
]


@pytest.fixture
def book(ctx, tmp_path):
    ctx.settings.chunk_size_tokens = 120
    ctx.settings.chunk_overlap_tokens = 10
    ctx.settings.top_k = 1  # only the best search hit: lookups must find the rest
    kb = create_knowledge_base(ctx, "CA")
    path = make_pdf(tmp_path / "book.pdf", PAGES)
    _, job_id, _ = register_upload(ctx, kb, path, "Book of Questions.pdf")
    run_ingest_job(ctx, job_id)
    return kb


def lookups(evidence):
    return [c for c in evidence.used if c.source == "lookup"]


def test_structure_is_stored_at_upload(ctx, book):
    with ctx.db() as conn:
        rows = conn.execute("SELECT label, question_count FROM doc_contents").fetchall()
        refs = conn.execute("SELECT short_key, is_header, chapter FROM doc_references").fetchall()
    assert [tuple(r) for r in rows][-1] == ("Mix", 6)
    assert ("rtp may 2025 q 5", 1, "1") in [tuple(r) for r in refs]


def test_lookup_is_on_by_default_and_can_be_turned_off(ctx, book):
    from adaptive_rag.config import Settings

    assert Settings(_env_file=None).structured_lookup is True  # default since 2026-11-09
    ctx.settings.structured_lookup = False
    question = "What does RTP May 2025 Q.5 ask in Chapter 1?"
    off = retrieve_evidence(ctx, book, question)
    assert "lookup" not in off.info and not lookups(off)


def test_an_exact_reference_brings_its_question_first(ctx, book):
    ctx.settings.structured_lookup = True
    evidence = retrieve_evidence(ctx, book, "What does RTP May 2025 Q.5 ask in Chapter 1?")
    found = lookups(evidence)
    assert found and evidence.used[0].source == "lookup"
    text = " ".join(c.text for c in found)
    assert "RTP - May 2025, Q.5 Notebook Page No." in text
    assert "significant accounting policies" in text  # the question itself, possibly next chunk
    [match] = evidence.info["lookup"]["matches"]
    assert match["page"] == 2 and match["chapter"] == "1"


def test_contents_row_and_printed_count(ctx, book):
    ctx.settings.structured_lookup = True
    evidence = retrieve_evidence(
        ctx, book, "Which pages cover AS 20 Earnings Per Share in the Book of Questions?"
    )
    [match] = evidence.info["lookup"]["matches"]
    assert match["kind"] == "contents" and match["label"] == "4.5" and match["count"] == 4
    [chunk] = [c for c in evidence.used if c.chunk_id == match["chunk"]]  # added, or already there
    assert "AS 20 - Earnings Per Share 4 5 - 6" in chunk.text
    assert "No. of Qs Page number" in (chunk.context_text or "") + chunk.text  # header present

    counted = retrieve_evidence(ctx, book, "How many questions are in revision case studies?")
    [match] = counted.info["lookup"]["matches"]
    assert match["label"] == "Mix" and match["count"] == 6  # printed, never computed


def test_listing_returns_the_printed_question_index(ctx, book):
    ctx.settings.structured_lookup = True
    evidence = retrieve_evidence(ctx, book, "Which questions cover Introduction to Standards?")
    [match] = evidence.info["lookup"]["matches"]
    assert match["kind"] == "listing" and match["entries"] == 2
    [chunk] = [c for c in evidence.used if c.chunk_id == match["chunk"]]
    assert "Question index" in chunk.text


def test_an_ambiguous_reference_is_skipped(ctx, tmp_path):
    ctx.settings.structured_lookup = True
    kb = create_knowledge_base(ctx, "Many")
    topics = ["Leases", "Inventories", "Revenue", "Borrowing Costs", "Segments"]
    pages = [
        [(topic, 12), ("01 RTP - May 2025, Q.5 Notebook Page No.", 9), (FILLER, 9)]
        for topic in topics
    ]
    _, job_id, _ = register_upload(ctx, kb, make_pdf(tmp_path / "many.pdf", pages), "many.pdf")
    run_ingest_job(ctx, job_id)
    evidence = retrieve_evidence(ctx, kb, "What is RTP May 2025 Q.5?")
    assert not lookups(evidence)
    assert evidence.info["lookup"]["skipped"][0]["candidates"] == 5


def test_generic_documents_and_questions_are_unchanged(ctx, tmp_path):
    kb = create_knowledge_base(ctx, "Prose")
    path = tmp_path / "notes.txt"
    path.write_text("Revenue grew because subscriptions expanded in every region this year.\n")
    _, job_id, _ = register_upload(ctx, kb, path, "notes.txt")
    run_ingest_job(ctx, job_id)
    question = "Why did revenue grow?"
    ctx.settings.structured_lookup = False
    off = retrieve_evidence(ctx, kb, question)
    ctx.settings.structured_lookup = True
    on = retrieve_evidence(ctx, kb, question)
    assert [c.chunk_id for c in on.used] == [c.chunk_id for c in off.used]
    assert on.info["lookup"] == {"matches": [], "skipped": []}


def test_another_knowledge_base_is_never_searched(ctx, book):
    ctx.settings.structured_lookup = True
    other = create_knowledge_base(ctx, "Other")
    evidence = retrieve_evidence(ctx, other, "What does RTP May 2025 Q.5 ask in Chapter 1?")
    assert not lookups(evidence) and evidence.used == []


def test_budget_is_respected(ctx, book):
    ctx.settings.structured_lookup = True
    ctx.settings.top_k = 3
    ctx.settings.evidence_max_tokens = 200
    evidence = retrieve_evidence(ctx, book, "What does RTP May 2025 Q.5 ask in Chapter 1?")
    assert sum(c.evidence_tokens for c in evidence.used) <= 200
    assert lookups(evidence)  # the exact match is kept; weaker search hits make room


def test_answer_cites_the_lookup_page_and_an_exact_match_passes_the_gate(ctx, book):
    ctx.settings.structured_lookup = True
    ctx.settings.score_floor, ctx.settings.score_floors = 0.99, {}  # search alone would refuse
    ctx.llm.queue(answer="It asks why policies are disclosed in one place [E1].")
    result = answer_question(ctx, book, "What does RTP May 2025 Q.5 ask in Chapter 1?")
    assert result.status == "answered"
    assert result.citations[0].source == "lookup" and result.citations[0].locator_start == 2


def test_a_follow_up_keeps_the_reference(ctx, book):
    ctx.settings.structured_lookup = True
    ctx.llm.queue()
    first = answer_question(ctx, book, "What does RTP May 2025 Q.5 ask in Chapter 1?")
    ctx.llm.queue()
    second = answer_question(ctx, book, "what is the answer", previous_trace_id=first.trace_id)
    with ctx.db() as conn:
        info = json.loads(
            conn.execute(
                "SELECT retrieval FROM query_traces WHERE id = ?", (second.trace_id,)
            ).fetchone()[0]
        )
    assert info["lookup"]["matches"][0]["label"] == "RTP - May 2025, Q.5"


def test_backfill_parses_documents_indexed_before_stage_5b(ctx, book):
    with ctx.db() as conn:
        conn.execute("DELETE FROM doc_contents")
        conn.execute("DELETE FROM doc_references")
        conn.execute("UPDATE documents SET structure_version = NULL")
        done = backfill(conn)
        assert done == [("Book of Questions.pdf", 5, 4)]  # 2 index lines + 2 question headers
        assert backfill(conn) == []  # already current
        assert conn.execute("SELECT COUNT(*) FROM doc_contents").fetchone()[0] == 5


def test_eval_runs_record_lookup_and_old_runs_count_as_without():
    old = {"retrieval": "baseline"}
    assert resume_conflicts(old, {"retrieval": "baseline", "structured_lookup": False}) == []
    assert resume_conflicts(old, {"retrieval": "baseline", "structured_lookup": True}) == [
        "structured_lookup"
    ]


# ---------------------------------------------------------------- bare index titles (opt-in)


def bare(ctx, kb, question):
    evidence = retrieve_evidence(ctx, kb, question)
    return [(m["label"], m.get("trigger")) for m in evidence.info["lookup"]["matches"]], evidence


def test_bare_titles_are_on_by_default_and_can_be_turned_off(ctx, book):
    from adaptive_rag.config import Settings

    assert Settings(_env_file=None).lookup_bare_titles is True  # default since 2026-11-09
    ctx.settings.structured_lookup = True
    ctx.settings.lookup_bare_titles = False
    assert bare(ctx, book, "Revision case studies")[0] == []


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Revision case studies", [("Mix", "bare_title")]),
        ("Branch Accounts in the Book of Questions", [("15", "bare_title")]),
        ("branch accounts", [("15", "bare_title")]),
        # Not an index request: a question word, part of a title, words that don't name the
        # document, or too long to be a title.
        ("Explain branch accounts", []),
        ("Branch", []),
        ("Branch Accounts in the Annual Report", []),
        ("Branch accounts for a large retailer with many outlets across several states", []),
    ],
)
def test_a_bare_title_triggers_only_on_a_whole_title(ctx, book, question, expected):
    ctx.settings.structured_lookup = True
    ctx.settings.lookup_bare_titles = True
    matches, evidence = bare(ctx, book, question)
    assert matches == expected
    if expected:
        [match] = evidence.info["lookup"]["matches"]
        assert any(c.chunk_id == match["chunk"] for c in evidence.used)


def test_a_named_document_wins_between_two_books_with_the_same_title(ctx, book, tmp_path):
    ctx.settings.structured_lookup = True
    ctx.settings.lookup_bare_titles = True
    other = [("Choice Based Questions", 14), *CONTENTS[1:]]
    path = make_pdf(tmp_path / "choice.pdf", [other, *PAGES[1:]])
    _, job_id, _ = register_upload(ctx, book, path, "Choice Based Questions.pdf")
    run_ingest_job(ctx, job_id)
    named, _ = bare(ctx, book, "Branch Accounts in the Book of Questions")
    both, _ = bare(ctx, book, "Branch Accounts")
    assert len(named) == 1 and len(both) == 2
    with ctx.db() as conn:
        books = dict(conn.execute("SELECT filename, id FROM documents").fetchall())
    _, evidence = bare(ctx, book, "Branch Accounts in the Book of Questions")
    [match] = evidence.info["lookup"]["matches"]
    assert match["chunk"].startswith(f"{books['Book of Questions.pdf']}-")
