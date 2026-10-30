import pytest

from adaptive_rag.ingest import register_upload, run_ingest_job
from adaptive_rag.knowledge_bases import EmbeddingModelMismatch, create_knowledge_base
from adaptive_rag.retrieval import RetrievedChunk, fit_to_budget, retrieve_baseline


def add(ctx, kb, tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    document, job_id, _ = register_upload(ctx, kb, path, name)
    run_ingest_job(ctx, job_id)
    return document["id"]


@pytest.fixture
def kb(ctx):
    return create_knowledge_base(ctx, "KB")


def test_finds_the_relevant_document_first(ctx, kb, tmp_path):
    add(ctx, kb, tmp_path, "cats.txt", "Cats purr and chase mice around the barn.")
    dogs = add(ctx, kb, tmp_path, "dogs.txt", "Dogs bark loudly at the mail carrier.")
    results = retrieve_baseline(ctx, kb, "why do dogs bark at the mail carrier", 2)
    assert results[0].document_id == dogs and results[0].filename == "dogs.txt"
    assert results[0].score > results[1].score
    assert results[0].source == "direct"


def test_respects_k_and_handles_small_collections(ctx, kb, tmp_path):
    add(ctx, kb, tmp_path, "a.txt", "One short document.")
    assert len(retrieve_baseline(ctx, kb, "document", 5)) == 1
    add(ctx, kb, tmp_path, "b.txt", "Another short document.")
    assert len(retrieve_baseline(ctx, kb, "document", 1)) == 1


def test_empty_kb_returns_nothing(ctx, kb):
    assert retrieve_baseline(ctx, kb, "anything", 5) == []


def test_knowledge_bases_are_isolated(ctx, kb, tmp_path):
    other = create_knowledge_base(ctx, "Other")
    add(ctx, other, tmp_path, "secret.txt", "The merger closes in March.")
    add(ctx, kb, tmp_path, "public.txt", "Lunch is served at noon.")
    results = retrieve_baseline(ctx, kb, "when does the merger close", 5)
    assert [result.filename for result in results] == ["public.txt"]


def test_documents_that_are_not_ready_are_not_searched(ctx, kb, tmp_path):
    document_id = add(ctx, kb, tmp_path, "a.txt", "Revenue grew strongly.")
    with ctx.db() as conn:
        conn.execute("UPDATE documents SET status = 'indexing' WHERE id = ?", (document_id,))
    assert retrieve_baseline(ctx, kb, "revenue", 5) == []


def test_embedding_mismatch_is_refused(ctx, kb):
    ctx.embedder.digest = "changed"
    with pytest.raises(EmbeddingModelMismatch):
        retrieve_baseline(ctx, kb, "anything", 5)


def chunk(chunk_id, tokens):
    return RetrievedChunk(chunk_id, 1, "a.txt", 0, "text", tokens, 0.9, "line", 1, 1, None)


def test_budget_never_exceeded_and_chunks_stay_whole():
    selected = fit_to_budget([chunk("a", 300), chunk("b", 300), chunk("c", 100)], 450)
    assert [item.chunk_id for item in selected] == ["a", "c"]


def test_top_five_full_chunks_fit_the_maximum_budget(settings):
    chunks = [chunk(str(i), settings.chunk_size_tokens) for i in range(settings.top_k)]
    assert len(fit_to_budget(chunks, settings.evidence_max_tokens)) == settings.top_k
