"""Registry matching, staleness, reuse and re-test decisions, and adaptive ingestion."""

import json
from dataclasses import replace

from adaptive_rag.context import AppContext
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.optimizer.candidates import BY_ID
from adaptive_rag.optimizer.profile import PROFILE_VERSION, Profile
from adaptive_rag.optimizer.registry import (
    EmbeddingContext,
    compare,
    eligible_entries,
    find_match,
    mark_stale,
)
from adaptive_rag.vectorstore import VectorStore
from fakes import FakeEmbeddings, QuestionLLM

BASE = Profile(
    version=PROFILE_VERSION,
    format="pdf",
    pages=40,
    tokens=20_000,
    sections=30,
    heading_density=1.5,
    median_section_tokens=400.0,
    section_coverage=0.9,
    table_count=4,
    table_share=0.05,
    chars_per_page=2500.0,
    language="en",
    headings_reliable=True,
    has_tables=True,
)
CONTEXT = EmbeddingContext("fake-embed:1", "abcdef123456", "fake-1", "pdf-5")


def add_entry(conn, profile=BASE, candidate="C3", context=CONTEXT, version=None, source="a.pdf"):
    c = BY_ID[candidate]
    return conn.execute(
        "INSERT INTO chunking_registry (candidate_id, strategy, size_tokens, overlap_tokens,"
        " chunker_version, embedding_model, embedding_digest, embedding_prompt_version,"
        " extractor_version, profile_version, profile, question_count, runtime_s,"
        " source_document) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 40, 300, ?)",
        (
            c.id,
            c.strategy,
            c.size,
            c.overlap,
            version or c.version,
            context.model,
            context.digest,
            context.prompt_version,
            context.extractor_version,
            PROFILE_VERSION,
            json.dumps(profile.to_dict()),
            source,
        ),
    ).lastrowid


# ---------------------------------------------------------------- matching rules


def test_profile_comparison_strong_borderline_different():
    assert compare(BASE, BASE.to_dict())[0] == "strong"
    near = replace(BASE, table_share=0.065, heading_density=2.0)
    assert compare(near, BASE.to_dict())[0] == "strong"
    borderline = replace(BASE, table_share=0.09, chars_per_page=5000.0)
    assert compare(borderline, BASE.to_dict())[0] == "borderline"
    far = replace(BASE, chars_per_page=9000.0)
    assert compare(far, BASE.to_dict())[0] == "different"
    for change in ({"format": "docx"}, {"has_tables": False}, {"headings_reliable": False}):
        assert compare(replace(BASE, **change), BASE.to_dict())[0] == "different"


def test_find_match_picks_the_closest_and_maps_to_actions(conn):
    add_entry(conn, replace(BASE, chars_per_page=3500.0), "C7", source="far.pdf")
    add_entry(conn, BASE, "C3", source="near.pdf")
    match = find_match(BASE, eligible_entries(conn, CONTEXT))
    assert (match.action, match.candidate_id) == ("reuse", "C3")
    borderline = find_match(replace(BASE, table_share=0.09), eligible_entries(conn, CONTEXT))
    assert borderline.action == "retest"
    assert find_match(replace(BASE, format="txt"), eligible_entries(conn, CONTEXT)).action == (
        "optimize"
    )


def test_entries_for_other_embeddings_or_old_chunkers_are_not_eligible(conn):
    add_entry(conn, context=replace(CONTEXT, digest="other"))
    add_entry(conn, version="recursive-0")
    add_entry(conn, context=replace(CONTEXT, extractor_version="pdf-4"))
    assert eligible_entries(conn, CONTEXT) == []


def test_mark_stale_on_embedding_or_chunker_change(conn):
    add_entry(conn)
    add_entry(conn, version="recursive-0")
    assert mark_stale(conn, CONTEXT) == 1
    assert mark_stale(conn, replace(CONTEXT, model="new-embed:1")) == 1
    stale = [r["stale"] for r in conn.execute("SELECT stale FROM chunking_registry")]
    assert stale == [1, 1]


# ---------------------------------------------------------------- adaptive ingestion


def table_report(i: int) -> str:
    lines = [
        f"Line {j} of report {i} says regional widget sales changed by a set amount."
        for j in range(400)
    ]
    table = ["Results by segment", "(in millions)", "2024 2023 2022"] + [
        f"Segment {name} revenue {k},480 {k},509 {k},210" for k, name in enumerate("abcdef", 1)
    ]
    return "\n".join(lines[:200] + [""] + table + [""] + lines[200:])


def adaptive_ctx(settings, llm=None):
    settings.chunking = "adaptive"
    return AppContext(
        settings, FakeEmbeddings(), llm or QuestionLLM(), VectorStore(settings.chroma_dir)
    )


def ingest(ctx, kb, tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    document, job_id, _ = register_upload(ctx, kb, path, name)
    run_ingest_job(ctx, job_id)
    with ctx.db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (document["id"],)).fetchone()
        run = conn.execute(
            "SELECT * FROM optimization_runs WHERE document_id = ?", (document["id"],)
        ).fetchone()
        config = conn.execute(
            "SELECT * FROM chunking_configs WHERE id = ?", (doc["chunking_config_id"],)
        ).fetchone()
    return doc, run, config


def test_first_document_is_optimized_and_a_similar_one_reuses(settings, conn, tmp_path):
    llm = QuestionLLM()
    ctx = adaptive_ctx(settings, llm)
    kb = create_knowledge_base(ctx, "KB")
    doc, run, config = ingest(ctx, kb, tmp_path, "a.txt", table_report(1))
    assert doc["status"] == "ready", doc["error"]
    assert run["action"] == "optimize" and run["registry_id"]
    assert config["strategy"] == BY_ID[run["candidate_id"]].strategy
    calls = llm.calls
    assert calls > 0

    doc2, run2, _ = ingest(ctx, kb, tmp_path, "b.txt", table_report(2))
    assert doc2["status"] == "ready"
    assert (run2["action"], run2["candidate_id"]) == ("reuse", run["candidate_id"])
    assert llm.calls == calls  # reuse makes no LLM calls
    with ctx.db() as c:
        assert c.execute("SELECT times_reused FROM chunking_registry").fetchone()[0] == 1


def test_borderline_match_runs_the_cheap_retest(settings, conn, tmp_path):
    ctx = adaptive_ctx(settings)
    kb = create_knowledge_base(ctx, "KB")
    with ctx.db() as c:
        add_entry(
            c,
            candidate="C3",
            context=EmbeddingContext("fake-embed:1", "abcdef123456", "fake-1", "txt-1"),
        )
    # Make the stored profile borderline for this document: same structure, different density.
    from adaptive_rag.loaders import LOADERS
    from adaptive_rag.optimizer.profile import profile_document

    path = tmp_path / "probe.txt"
    path.write_text(table_report(3))
    profile = profile_document(LOADERS["txt"].extract(path), "txt")
    stored = replace(profile, chars_per_page=None, table_share=profile.table_share + 0.04)
    with ctx.db() as c:
        c.execute(
            "UPDATE chunking_registry SET profile = ?, extractor_version = ?",
            (json.dumps(stored.to_dict()), LOADERS["txt"].version),
        )
    doc, run, _ = ingest(ctx, kb, tmp_path, "c.txt", table_report(3))
    assert doc["status"] == "ready", doc["error"]
    detail = json.loads(run["detail"])
    assert detail["match"]["action"] == "retest"
    assert run["action"] in ("retest-kept", "optimize")
    assert "retest" in detail


def test_forced_and_fixed_modes_skip_the_optimizer(settings, conn, tmp_path):
    llm = QuestionLLM()
    ctx = adaptive_ctx(settings, llm)
    ctx.settings.chunking = "C7"
    kb = create_knowledge_base(ctx, "KB")
    _, run, config = ingest(ctx, kb, tmp_path, "a.txt", table_report(1))
    assert (run["action"], config["strategy"]) == ("forced", "table_aware")
    ctx.settings.chunking = "fixed"
    _, run, config = ingest(ctx, kb, tmp_path, "b.txt", table_report(2))
    assert (run["action"], config["strategy"]) == ("fixed", "fixed")
    assert llm.calls == 0


def test_embedding_change_makes_entries_stale_and_triggers_optimization(settings, conn, tmp_path):
    ctx = adaptive_ctx(settings)
    kb = create_knowledge_base(ctx, "KB")
    ingest(ctx, kb, tmp_path, "a.txt", table_report(1))
    ctx.embedder.digest = "re-pulled-weights"
    kb2 = create_knowledge_base(ctx, "KB2")
    _, run, _ = ingest(ctx, kb2, tmp_path, "b.txt", table_report(2))
    assert run["action"] == "optimize"
    assert json.loads(run["detail"])["marked_stale"] == 1
