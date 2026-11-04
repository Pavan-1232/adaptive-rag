"""C7's table header context is charged to every budget: Recall@budget and the LLM evidence."""

from adaptive_rag.answering.prompts import build_messages
from adaptive_rag.chunking import chunk_table_aware, count_tokens, embedding_text
from adaptive_rag.evaluation.metrics import RankedChunk, Span, recall_at_budget
from adaptive_rag.evaluation.runner import _ranked
from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import create_knowledge_base
from adaptive_rag.loaders import ExtractedDocument, Unit
from adaptive_rag.retrieval import RetrievedChunk, fit_to_budget, retrieve_baseline

HEADER = "Table 1. Segment results by quarter\n(in millions)\n2024 2023 2022\n"


def table_doc(rows=120) -> ExtractedDocument:
    text = HEADER + "\n".join(
        f"Segment item {i} revenue {i},101 {i},202 ({i},303)" for i in range(rows)
    )
    return ExtractedDocument(text, "line", [Unit(1, 0, len(text))])


def retrieved(token_count, context_text=None, context_tokens=0, start=0, end=10) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c",
        document_id=1,
        filename="doc.pdf",
        chunk_index=0,
        text="body",
        token_count=token_count,
        score=0.9,
        locator_kind="page",
        locator_start=1,
        locator_end=1,
        section_heading=None,
        start_char=start,
        end_char=end,
        context_text=context_text,
        context_tokens=context_tokens,
    )


def test_continuation_chunks_carry_their_context_cost():
    doc = table_doc()
    continuation = [c for c in chunk_table_aware(doc, 256, 0) if c.context_start is not None]
    assert continuation
    for chunk in continuation:
        context = doc.text[chunk.context_start : chunk.context_end]
        assert chunk.context_tokens == count_tokens(context + "\n") > 0
        assert chunk.evidence_tokens == chunk.token_count + chunk.context_tokens
        # What is embedded and read costs no more than what is charged.
        assert count_tokens(embedding_text(doc.text, chunk)) <= chunk.evidence_tokens
        assert chunk.evidence_tokens <= 256


def test_llm_evidence_budget_charges_context():
    chunk = retrieved(100, context_text="Table 1. Header", context_tokens=50)
    assert (
        fit_to_budget([chunk], 140) == []
    )  # the text alone (100) would fit; with context it doesn't
    assert fit_to_budget([chunk], 150) == [chunk]


def test_llm_sees_the_context_before_the_chunk():
    chunk = retrieved(10, context_text="Table 1. Header\n2024 2023", context_tokens=8)
    content = build_messages("question?", [chunk])[1]["content"]
    assert "Table 1. Header\n2024 2023\nbody" in content


def test_recall_at_budget_charges_context():
    evidence = [Span("doc.pdf", 0, 10)]
    ranked = _ranked([retrieved(100, context_text="Header", context_tokens=50)])
    assert ranked[0].token_count == 150
    assert recall_at_budget(ranked, evidence, 140) == 0.0
    assert recall_at_budget(ranked, evidence, 150) == 1.0


def test_context_adds_cost_but_no_coverage():
    # Gold evidence that sits only in the header range is not covered by the chunk's own range.
    evidence = [Span("doc.pdf", 0, 20)]
    ranked = [RankedChunk("doc.pdf", 100, 200, 150)]
    assert recall_at_budget(ranked, evidence, 1000) == 0.0


def test_stored_context_comes_back_from_retrieval(ctx, tmp_path):
    kb = create_knowledge_base(ctx, "KB")
    path = tmp_path / "a.txt"
    path.write_text("Quarterly revenue by segment.")
    _, job_id, _ = register_upload(ctx, kb, path, "a.txt")
    run_ingest_job(ctx, job_id)
    with ctx.db() as conn:
        conn.execute("UPDATE chunks SET context_text = 'Header row', context_tokens = 7")
    [chunk] = retrieve_baseline(ctx, kb, "revenue", 1)
    assert chunk.context_text == "Header row"
    assert chunk.evidence_tokens == chunk.token_count + 7
    assert chunk.evidence_text == "Header row\n" + chunk.text
