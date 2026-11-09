import time

import pytest
from fastapi.testclient import TestClient

from adaptive_rag.api import create_app
from adaptive_rag.providers import ProviderUnavailable
from documents import make_docx, make_pdf, make_scanned_pdf


@pytest.fixture
def client(ctx):
    with TestClient(create_app(ctx)) as test_client:
        yield test_client


@pytest.fixture
def kb_id(client):
    return client.post("/kbs", json={"name": "MBA"}).json()["id"]


def upload(client, kb_id, name, content):
    return client.post(f"/kbs/{kb_id}/documents", files={"file": (name, content)})


def test_full_flow_for_all_three_formats(client, ctx, kb_id, tmp_path):
    pdf = make_pdf(
        tmp_path / "a.pdf",
        [
            [("Filler page about nothing relevant here", 11)],
            [("The pdf revenue figure grew strongly", 11)],
        ],
    )
    docx_file = make_docx(
        tmp_path / "b.docx", [("Heading 1", "Plan"), ("Normal", "The docx hiring plan expands")]
    )
    files = {
        "a.pdf": (pdf.read_bytes(), "pdf revenue figure", "a.pdf, p"),
        "b.docx": (docx_file.read_bytes(), "docx hiring plan", 'b.docx, "Plan", para'),
        "c.txt": (b"The txt pricing note rises.", "txt pricing note", "c.txt, line 1"),
    }
    for name, (content, _, _) in files.items():
        response = upload(client, kb_id, name, content)
        assert response.status_code == 202
        job = client.get(f"/jobs/{response.json()['job_id']}").json()
        assert job["status"] == "succeeded", job

    for name, (_, question, label) in files.items():
        ctx.llm.queue(answer="Found it [E1].")
        body = client.post(f"/kbs/{kb_id}/query", json={"question": question}).json()
        assert body["status"] == "answered", name
        assert body["citations"][0]["label"].startswith(label)
        assert body["trace_id"] > 0


def test_pdf_citation_has_the_correct_page(client, ctx, kb_id, tmp_path):
    ctx.settings.chunk_size_tokens = 20
    ctx.settings.chunk_overlap_tokens = 0
    pages = [
        [("Filler about the weather and gardens and birds in the spring season. " * 6, 11)],
        [("Filler about trains and railways and timetables across the country. " * 6, 11)],
        [("Quarterly revenue grew strongly because enterprise subscriptions expanded. " * 6, 11)],
    ]
    pdf = make_pdf(tmp_path / "a.pdf", pages)
    upload(client, kb_id, "a.pdf", pdf.read_bytes())
    ctx.llm.queue(answer="Grew [E1].")
    question = {"question": "quarterly revenue enterprise subscriptions"}
    citation = client.post(f"/kbs/{kb_id}/query", json=question).json()["citations"][0]
    assert (citation["locator_start"], citation["locator_end"]) == (3, 3)
    assert citation["label"] == "a.pdf, p. 3"


def test_list_and_delete_document(client, kb_id):
    document = upload(client, kb_id, "a.txt", b"Some content.").json()["document"]
    listed = client.get(f"/kbs/{kb_id}/documents").json()
    assert [item["id"] for item in listed] == [document["id"]]
    assert listed[0]["status"] == "ready" and "canonical_text" not in listed[0]
    assert client.delete(f"/documents/{document['id']}").status_code == 204
    assert client.get(f"/kbs/{kb_id}/documents").json() == []
    assert client.delete(f"/documents/{document['id']}").status_code == 404


def test_cannot_delete_while_indexing(client, ctx, kb_id):
    document = upload(client, kb_id, "a.txt", b"Some content.").json()["document"]
    with ctx.db() as conn:
        conn.execute("UPDATE documents SET status = 'indexing' WHERE id = ?", (document["id"],))
    assert client.delete(f"/documents/{document['id']}").status_code == 409


def test_duplicate_upload_is_reported(client, kb_id):
    first = upload(client, kb_id, "a.txt", b"Same bytes.").json()
    second = upload(client, kb_id, "b.txt", b"Same bytes.").json()
    assert second["duplicate"] is True and second["job_id"] is None
    assert second["document"]["id"] == first["document"]["id"]


@pytest.mark.parametrize(
    ("name", "content"),
    [("a.exe", b"MZ"), ("a.pdf", b"fake"), ("a.docx", b"fake"), ("a.txt", b"")],
)
def test_bad_uploads_get_400(client, kb_id, name, content):
    assert upload(client, kb_id, name, content).status_code == 400


def test_oversized_upload_gets_413(client, ctx, kb_id):
    ctx.settings.max_upload_bytes = 10
    assert upload(client, kb_id, "a.txt", b"x" * 100).status_code == 413


def test_extraction_failure_is_visible_on_job_and_document(client, kb_id, tmp_path):
    scan = make_scanned_pdf(tmp_path / "scan.pdf").read_bytes()
    body = upload(client, kb_id, "scan.pdf", scan).json()
    assert "OCR" in client.get(f"/jobs/{body['job_id']}").json()["error"]
    assert client.get(f"/kbs/{kb_id}/documents").json()[0]["status"] == "failed"


def test_kb_validation_and_conflicts(client, kb_id):
    assert client.post("/kbs", json={"name": "MBA"}).status_code == 409
    assert client.post("/kbs", json={"name": "   "}).status_code == 422
    assert [kb["name"] for kb in client.get("/kbs").json()] == ["MBA"]


def test_unknown_ids_get_404(client):
    assert client.get("/kbs/99/documents").status_code == 404
    assert client.post("/kbs/99/query", json={"question": "x"}).status_code == 404
    assert client.get("/jobs/99").status_code == 404


def test_blank_question_rejected(client, kb_id):
    assert client.post(f"/kbs/{kb_id}/query", json={"question": "  "}).status_code == 422


def test_query_is_scoped_to_its_kb(client, ctx, kb_id):
    other = client.post("/kbs", json={"name": "Other"}).json()["id"]
    upload(client, other, "secret.txt", b"The merger closes in March.")
    body = client.post(f"/kbs/{kb_id}/query", json={"question": "merger closes March"}).json()
    assert body["status"] == "insufficient" and ctx.llm.calls == []


def test_provider_outage_gets_503(client, ctx, kb_id):
    upload(client, kb_id, "a.txt", b"Some content.")
    ctx.embedder.fail_with = ProviderUnavailable("Ollama is not running.")
    response = client.post(f"/kbs/{kb_id}/query", json={"question": "content"})
    assert response.status_code == 503 and "not running" in response.json()["detail"]


def test_outage_during_upload_marks_document_failed(client, ctx, kb_id):
    ctx.embedder.fail_with = ProviderUnavailable("Ollama is not running.")
    document = upload(client, kb_id, "a.txt", b"Some content.").json()["document"]
    listed = client.get(f"/kbs/{kb_id}/documents").json()
    assert listed[0]["id"] == document["id"] and listed[0]["status"] == "failed"
    assert "not running" in listed[0]["error"]


def test_bad_model_output_gets_502(client, ctx, kb_id):
    upload(client, kb_id, "a.txt", b"Revenue grew strongly.")
    ctx.llm.responses.append("not json")
    response = client.post(f"/kbs/{kb_id}/query", json={"question": "revenue grew"})
    assert response.status_code == 502


def test_embedding_model_change_gets_409(client, ctx, kb_id):
    ctx.embedder.digest = "changed"
    assert client.post(f"/kbs/{kb_id}/query", json={"question": "x"}).status_code == 409


def test_health_reports_degraded_when_model_unavailable(client, ctx):
    assert client.get("/health").json()["status"] == "ok"
    ctx.llm.fail_with = ProviderUnavailable("down")
    body = client.get("/health").json()
    assert body == {
        "status": "degraded",
        "database": True,
        "embedding_model": True,
        "llm_model": False,
        "cloud_keys": {"openai": False, "gemini": False, "anthropic": False},
        "default_provider": "ollama",
    }


def test_startup_requeues_interrupted_work(settings, ctx):
    with TestClient(create_app(ctx)) as client:
        kb_id = client.post("/kbs", json={"name": "KB"}).json()["id"]
        document = upload(client, kb_id, "a.txt", b"Resume me.").json()["document"]
        with ctx.db() as conn:
            conn.execute("UPDATE documents SET status = 'indexing' WHERE id = ?", (document["id"],))
    with TestClient(create_app(ctx)) as client:
        for _ in range(50):
            status = client.get(f"/kbs/{kb_id}/documents").json()[0]["status"]
            if status == "ready":
                break
            time.sleep(0.05)
        assert status == "ready"
