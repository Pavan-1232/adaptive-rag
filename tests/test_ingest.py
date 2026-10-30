import pytest

from adaptive_rag.ingest import (
    VersionInProgress,
    delete_document,
    register_upload,
    repair_on_startup,
    run_ingest_job,
)
from adaptive_rag.knowledge_bases import (
    EmbeddingModelMismatch,
    KnowledgeBaseExists,
    check_embedding_lock,
    create_knowledge_base,
)
from adaptive_rag.providers import EmbeddingInputTooLong, ProviderUnavailable
from documents import make_docx, make_pdf, make_scanned_pdf


@pytest.fixture
def kb(ctx):
    return create_knowledge_base(ctx, "MBA Materials")


def write_txt(tmp_path, content, name="upload.txt"):
    path = tmp_path / name
    path.write_text(content)
    return path


def ingest(ctx, kb, path, filename=None):
    document, job_id, duplicate = register_upload(ctx, kb, path, filename or path.name)
    if job_id:
        run_ingest_job(ctx, job_id)
    return get_doc(ctx, document["id"]), job_id, duplicate


def get_doc(ctx, document_id):
    with ctx.db() as conn:
        return conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()


def chunk_rows(ctx, document_id):
    with ctx.db() as conn:
        return conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)
        ).fetchall()


def test_txt_ingest_stores_chunks_and_vectors(ctx, kb, tmp_path):
    doc, _, duplicate = ingest(ctx, kb, write_txt(tmp_path, "# Intro\nRevenue grew. " * 400))
    assert doc["status"] == "ready" and not duplicate
    rows = chunk_rows(ctx, doc["id"])
    assert len(rows) > 1
    first = rows[0]
    assert first["section_heading"] == "Intro"
    assert first["chunking_config_id"] == doc["chunking_config_id"]
    assert doc["canonical_text"][first["start_char"] : first["end_char"]] == first["text"]
    assert ctx.store.document_counts(kb["collection_name"]) == {doc["id"]: len(rows)}


def test_pdf_and_docx_ingest(ctx, kb, tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [[("Revenue on page one " * 5, 11)], [("Costs " * 20, 11)]])
    docx_file = make_docx(tmp_path / "b.docx", [("Heading 1", "Plan"), ("Normal", "Text " * 30)])
    pdf_doc, _, _ = ingest(ctx, kb, pdf)
    docx_doc, _, _ = ingest(ctx, kb, docx_file)
    assert (pdf_doc["status"], pdf_doc["locator_kind"]) == ("ready", "page")
    assert (docx_doc["status"], docx_doc["locator_kind"]) == ("ready", "paragraph")
    assert chunk_rows(ctx, docx_doc["id"])[0]["section_heading"] == "Plan"


def test_duplicate_upload_returns_existing_without_new_job(ctx, kb, tmp_path):
    first, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Same content here."))
    second, job_id, duplicate = ingest(
        ctx, kb, write_txt(tmp_path, "Same content here.", "other.txt")
    )
    assert duplicate and job_id is None and second["id"] == first["id"]


def test_same_content_allowed_in_another_kb(ctx, kb, tmp_path):
    other = create_knowledge_base(ctx, "Research")
    path = write_txt(tmp_path, "Shared content here.")
    first, _, _ = ingest(ctx, kb, path)
    second, _, duplicate = ingest(ctx, other, path)
    assert not duplicate and second["id"] != first["id"]


def test_new_version_replaces_old_only_after_success(ctx, kb, tmp_path):
    old, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Version one text."))
    new, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Version two text."))
    assert new["version"] == 2 and new["status"] == "ready"
    assert get_doc(ctx, old["id"]) is None
    assert set(ctx.store.document_counts(kb["collection_name"])) == {new["id"]}


def test_failed_new_version_keeps_old_version_searchable(ctx, kb, tmp_path):
    old, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Version one text."))
    ctx.embedder.fail_with = ProviderUnavailable("Ollama is down")
    new, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Version two text."))
    assert new["status"] == "failed" and "Ollama is down" in new["error"]
    assert get_doc(ctx, old["id"])["status"] == "ready"
    assert ctx.store.document_counts(kb["collection_name"]) == {old["id"]: 1}


def test_failed_document_can_be_retried(ctx, kb, tmp_path):
    path = write_txt(tmp_path, "Retry this text.")
    ctx.embedder.fail_with = ProviderUnavailable("down")
    failed, _, _ = ingest(ctx, kb, path)
    assert failed["status"] == "failed"
    ctx.embedder.fail_with = None
    retried, job_id, duplicate = ingest(ctx, kb, path)
    assert retried["id"] == failed["id"] and retried["status"] == "ready"
    assert job_id is not None and not duplicate


def test_scanned_pdf_marks_document_failed_with_message(ctx, kb, tmp_path):
    doc, job_id, _ = ingest(ctx, kb, make_scanned_pdf(tmp_path / "scan.pdf"))
    assert doc["status"] == "failed" and "OCR" in doc["error"]
    with ctx.db() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    assert job["status"] == "failed" and "OCR" in job["error"]


def test_oversized_chunk_is_rejected_not_truncated(ctx, kb, tmp_path):
    ctx.embedder.fail_with = EmbeddingInputTooLong("too long")
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Some text here."))
    assert doc["status"] == "failed" and "limit" in doc["error"]
    assert ctx.store.document_counts(kb["collection_name"]) == {}


def test_unexpected_error_hides_details(ctx, kb, tmp_path):
    ctx.embedder.fail_with = RuntimeError("secret internal detail")
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Some text here."))
    assert doc["status"] == "failed" and "secret" not in doc["error"]


def test_llm_unloaded_after_ingest(ctx, kb, tmp_path):
    ingest(ctx, kb, write_txt(tmp_path, "Some text here."))
    assert ctx.llm.unloads == 1


def test_llm_unload_failure_does_not_fail_ingest(ctx, kb, tmp_path):
    def broken():
        raise ProviderUnavailable("down")

    ctx.llm.unload = broken
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Some text here."))
    assert doc["status"] == "ready"


def test_second_version_while_first_in_progress_is_refused(ctx, kb, tmp_path):
    register_upload(ctx, kb, write_txt(tmp_path, "Version one."), "a.txt")
    with pytest.raises(VersionInProgress):
        register_upload(ctx, kb, write_txt(tmp_path, "Version two."), "a.txt")


def test_path_in_filename_is_discarded(ctx, kb, tmp_path):
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Some text."), "../../evil.txt")
    assert doc["filename"] == "evil.txt"
    stored = {path.name for path in ctx.settings.files_dir.iterdir()}
    assert stored == {f"{doc['sha256']}.txt"}


def test_delete_removes_vectors_rows_and_unused_file(ctx, kb, tmp_path):
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Delete me please."))
    delete_document(ctx, doc["id"])
    assert get_doc(ctx, doc["id"]) is None and chunk_rows(ctx, doc["id"]) == []
    assert ctx.store.document_counts(kb["collection_name"]) == {}
    assert list(ctx.settings.files_dir.iterdir()) == []


def test_delete_keeps_file_used_by_another_kb(ctx, kb, tmp_path):
    other = create_knowledge_base(ctx, "Research")
    path = write_txt(tmp_path, "Shared file content.")
    first, _, _ = ingest(ctx, kb, path)
    ingest(ctx, other, path)
    delete_document(ctx, first["id"])
    assert len(list(ctx.settings.files_dir.iterdir())) == 1


def test_duplicate_kb_name_rejected(ctx, kb):
    with pytest.raises(KnowledgeBaseExists):
        create_knowledge_base(ctx, "MBA Materials")


def test_embedding_model_change_is_refused(ctx, kb, tmp_path):
    ctx.embedder.digest = "different"
    with pytest.raises(EmbeddingModelMismatch):
        check_embedding_lock(ctx, kb)
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Some text here."))
    assert doc["status"] == "failed"


def test_repair_requeues_interrupted_document(ctx, kb, tmp_path):
    document, job_id, _ = register_upload(ctx, kb, write_txt(tmp_path, "Interrupted."), "a.txt")
    with ctx.db() as conn:
        conn.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
        conn.execute("UPDATE documents SET status = 'indexing' WHERE id = ?", (document["id"],))
    job_ids = repair_on_startup(ctx)
    assert len(job_ids) == 1 and job_ids[0] != job_id
    run_ingest_job(ctx, job_ids[0])
    assert get_doc(ctx, document["id"])["status"] == "ready"


def test_repair_reindexes_ready_document_missing_vectors(ctx, kb, tmp_path):
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Vectors go missing."))
    ctx.store.delete_document(kb["collection_name"], doc["id"])
    job_ids = repair_on_startup(ctx)
    assert get_doc(ctx, doc["id"])["status"] == "pending"
    run_ingest_job(ctx, job_ids[0])
    assert ctx.store.document_counts(kb["collection_name"]) == {doc["id"]: 1}


def test_repair_removes_orphan_vectors_and_superseded_documents(ctx, kb, tmp_path):
    doc, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Keep this one."))
    ctx.store.add(
        kb["collection_name"],
        ["999-0"],
        [[1.0] + [0.0] * 255],
        [{"document_id": 999, "chunk_index": 0}],
    )
    gone, _, _ = ingest(ctx, kb, write_txt(tmp_path, "Old one.", "old.txt"))
    with ctx.db() as conn:
        conn.execute("UPDATE documents SET status = 'superseded' WHERE id = ?", (gone["id"],))
    assert repair_on_startup(ctx) == []
    assert get_doc(ctx, gone["id"]) is None
    assert set(ctx.store.document_counts(kb["collection_name"])) == {doc["id"]}
