"""Stage 7 backend: Host and origin checks, knowledge-base deletion, API keys in the OS keychain
(with a canary leak test), the evaluation summary, and same-origin UI serving."""

import json
import logging
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from adaptive_rag.api import create_app
from adaptive_rag.evaluation.summary import STAGE4_REPORT, STAGE5_REPORT, verdict
from adaptive_rag.providers.keys import KEYCHAIN_SERVICE, api_key

CANARY = "sk-CANARY-5d1e8b2c-never-log-this"
ORIGIN = {"origin": "http://testserver"}


@pytest.fixture
def client(ctx):
    with TestClient(create_app(ctx)) as test_client:
        yield test_client


def make_kb(client, name="KB"):
    return client.post("/kbs", json={"name": name}).json()


# ---------------------------------------------------------------- Host and origin checks


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.evil.example", "localhost:abc", ""])
def test_foreign_host_is_rejected(ctx, host):
    ctx.settings.allowed_hosts = ["127.0.0.1", "localhost"]
    with TestClient(create_app(ctx)) as client:
        response = client.get("/kbs", headers={"host": host})
    assert response.status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:5173", "localhost"])
def test_local_hosts_are_accepted(ctx, host):
    ctx.settings.allowed_hosts = ["127.0.0.1", "localhost"]
    with TestClient(create_app(ctx)) as client:
        assert client.get("/kbs", headers={"host": host}).status_code == 200


def test_default_settings_allow_only_local_hosts():
    from adaptive_rag.config import Settings

    assert Settings(_env_file=None).allowed_hosts == ["127.0.0.1", "localhost"]


def test_default_provider_setting(monkeypatch, client, ctx):
    from pydantic import ValidationError

    from adaptive_rag.config import Settings

    assert Settings(_env_file=None).default_provider == "ollama"
    monkeypatch.setenv("ADAPTIVE_RAG_DEFAULT_PROVIDER", "gemini")
    assert Settings(_env_file=None).default_provider == "gemini"
    monkeypatch.setenv("ADAPTIVE_RAG_DEFAULT_PROVIDER", "gemni")
    with pytest.raises(ValidationError):  # a typo fails at startup, not silently
        Settings(_env_file=None)

    assert client.get("/health").json()["default_provider"] == "ollama"
    ctx.settings.default_provider = "gemini"
    assert client.get("/health").json()["default_provider"] == "gemini"
    # The API's own default is unchanged: only the UI pre-selects the setting.
    kb = make_kb(client)
    ctx.llm.queue()
    body = client.post(f"/kbs/{kb['id']}/query", json={"question": "q"}).json()
    assert body["provider"] == "ollama"


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "http://evil.example"},
        {"origin": "null"},
        {"origin": "http://localhost:5173"},  # a different origin from the Host
        {"sec-fetch-site": "cross-site"},
        {"origin": "http://testserver", "sec-fetch-site": "same-site"},
    ],
)
def test_cross_site_changes_are_rejected(client, headers):
    assert client.post("/kbs", json={"name": "X"}, headers=headers).status_code == 403
    assert client.put("/keys/openai", json={"key": "abc"}, headers=headers).status_code == 403
    assert client.get("/kbs").json() == []


def test_same_origin_and_non_browser_changes_are_accepted(client):
    same = {"origin": "http://testserver", "sec-fetch-site": "same-origin"}
    assert client.post("/kbs", json={"name": "A"}, headers=same).status_code == 201
    assert client.post("/kbs", json={"name": "B"}).status_code == 201  # curl-style, no Origin


def test_api_prefix_reaches_the_same_routes(client):
    make_kb(client)
    assert client.get("/api/kbs").json() == client.get("/kbs").json()
    assert client.get("/api/keys").status_code == 200


# ---------------------------------------------------------------- knowledge-base deletion


def test_delete_kb_removes_documents_vectors_files_and_row(client, ctx):
    kb = make_kb(client)
    other = make_kb(client, "Other")
    for kb_id in (kb["id"], other["id"]):
        client.post(f"/kbs/{kb_id}/documents", files={"file": ("a.txt", b"Shared revenue text.")})
    client.post(f"/kbs/{kb['id']}/documents", files={"file": ("b.txt", b"Only in the first.")})
    with ctx.db() as conn:
        collection_of = dict(
            conn.execute("SELECT id, collection_name FROM knowledge_bases").fetchall()
        )
    stored = list(ctx.settings.files_dir.rglob("*.*"))
    assert len(stored) == 2

    assert client.delete(f"/kbs/{kb['id']}", headers=ORIGIN).status_code == 204

    assert [row["id"] for row in client.get("/kbs").json()] == [other["id"]]
    assert client.get(f"/kbs/{kb['id']}/documents").status_code == 404
    with ctx.db() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM documents WHERE kb_id = ?", (kb["id"],)).fetchone()[
                0
            ]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE d.kb_id = ?",
                (kb["id"],),
            ).fetchone()[0]
            == 0
        )
    names = {c.name for c in ctx.store._client.list_collections()}
    assert names == {collection_of[other["id"]]}
    # The shared file stays for the other knowledge base; the other one is removed.
    assert len(list(ctx.settings.files_dir.rglob("*.*"))) == 1
    assert client.get(f"/kbs/{other['id']}/documents").json()[0]["status"] == "ready"
    assert client.delete(f"/kbs/{kb['id']}").status_code == 404


def test_delete_kb_refuses_while_indexing(client, ctx):
    kb = make_kb(client)
    client.post(f"/kbs/{kb['id']}/documents", files={"file": ("a.txt", b"Some text.")})
    with ctx.db() as conn:
        conn.execute("UPDATE documents SET status = 'indexing'")
    assert client.delete(f"/kbs/{kb['id']}").status_code == 409
    assert len(client.get("/kbs").json()) == 1


def test_delete_empty_kb(client):
    kb = make_kb(client)
    assert client.delete(f"/kbs/{kb['id']}").status_code == 204
    assert client.get("/kbs").json() == []


# ---------------------------------------------------------------- API keys


def test_key_sources_and_keychain_precedence(client, ctx, memory_keyring):
    assert client.get("/keys").json() == {
        "openai": "not set",
        "gemini": "not set",
        "anthropic": "not set",
    }
    ctx.settings.gemini_api_key = SecretStr("env-key")
    assert client.get("/keys").json()["gemini"] == "env"

    assert client.put("/keys/gemini", json={"key": "  keychain-key "}).status_code == 204
    assert memory_keyring.items[(KEYCHAIN_SERVICE, "gemini")] == "keychain-key"
    assert client.get("/keys").json()["gemini"] == "keychain"
    assert api_key(ctx.settings, "gemini").get_secret_value() == "keychain-key"
    assert client.get("/health").json()["cloud_keys"]["gemini"] is True

    assert client.delete("/keys/gemini").status_code == 204
    assert client.get("/keys").json()["gemini"] == "env"
    assert api_key(ctx.settings, "gemini").get_secret_value() == "env-key"
    assert client.delete("/keys/gemini").status_code == 204  # already gone: not an error


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"nokey": 1}', b'{"key": 5}', b'{"key": ""}', b'{"key": "a b"}'],
)
def test_bad_key_requests_get_fixed_messages(client, body):
    response = client.put(
        "/keys/openai", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert client.get("/keys").json()["openai"] == "not set"


def test_unknown_provider_and_oversized_request(client):
    assert client.put("/keys/ollama", json={"key": "abc"}).status_code == 404
    assert client.delete("/keys/nope").status_code == 404
    assert client.put("/keys/openai", json={"key": "a" * 5000}).status_code == 413
    assert client.put("/keys/openai", json={"key": "a" * 513}).status_code == 400


def test_locked_keychain_falls_back_to_env_and_reports_safely(client, ctx, memory_keyring):
    ctx.settings.openai_api_key = SecretStr("env-key")
    memory_keyring.fail = True
    assert api_key(ctx.settings, "openai").get_secret_value() == "env-key"
    assert client.get("/keys").json()["openai"] == "env"
    saved = client.put("/keys/openai", json={"key": "abc"})
    assert saved.status_code == 503 and "keychain" in saved.json()["detail"]
    assert client.delete("/keys/openai").status_code == 503


def test_canary_key_never_leaks_from_key_endpoints(ctx, memory_keyring, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    ctx.store = None  # the app starts its own vector-store process, as in normal use
    with TestClient(create_app(ctx)) as client:
        texts, responses = _key_requests(client, memory_keyring)
    _assert_no_canary(ctx, texts, caplog, capsys)


def _key_requests(client, memory_keyring):
    texts = []
    kb = make_kb(client)
    client.post(f"/kbs/{kb['id']}/documents", files={"file": ("a.txt", b"Revenue text " * 50)})
    responses = [
        client.put("/keys/anthropic", json={"key": CANARY}),
        client.get("/keys"),
        client.get("/health"),
        client.put("/keys/anthropic", json={"key": CANARY + " x"}),  # invalid: has a space
        client.put("/keys/anthropic", json={"key": CANARY * 20}),  # invalid: too long
        client.put("/keys/anthropic", json={"key": CANARY, "extra": [CANARY]}),
        client.put("/keys/anthropic", content=CANARY.encode()),  # not JSON
        client.put("/keys/ollama", json={"key": CANARY}),  # unknown provider
        client.put("/keys/anthropic", json={"key": CANARY}, headers={"origin": "http://x"}),
    ]
    memory_keyring.fail = True
    responses.append(client.put("/keys/anthropic", json={"key": CANARY}))
    memory_keyring.fail = False
    assert [r.status_code for r in responses] == [204, 200, 200, 400, 400, 204, 400, 404, 403, 503]
    # The canary really is stored, so its absence everywhere else means something.
    assert memory_keyring.items[(KEYCHAIN_SERVICE, "anthropic")] == CANARY

    texts += [r.text for r in responses] + [str(dict(r.headers)) for r in responses]
    return texts, responses


def _assert_no_canary(ctx, texts, caplog, capsys):
    captured = capsys.readouterr()
    texts += [caplog.text, captured.out, captured.err]
    texts += [str(record.__dict__) for record in caplog.records]
    with ctx.db() as conn:
        texts.append("\n".join(conn.iterdump()))
    for path in ctx.settings.data_dir.rglob("*"):
        if path.is_file():
            texts.append(path.read_bytes().decode("latin-1"))
    texts += [repr(ctx.settings), ctx.settings.model_dump_json()]
    for text in texts:
        assert CANARY not in text, "the API key leaked"
        assert CANARY[:16] not in text, "part of the API key leaked"


# ---------------------------------------------------------------- evaluation summary


def test_verdicts_in_plain_words():
    assert verdict([0.1, 0.02, 0.2]) == "better than baseline"
    assert verdict([-0.1, -0.2, -0.01]) == "worse than baseline"
    assert verdict([0.0, 0.0, 0.0]) == "identical to baseline"
    assert verdict([0.167, 0.0, 0.5]).startswith("inconclusive")
    assert verdict([-0.019, -0.144, 0.106]).startswith("inconclusive")


def test_evaluation_summary_reads_the_committed_reports(client):
    body = client.get("/evaluation").json()
    stage4 = json.loads((Path("benchmarks/results") / STAGE4_REPORT).read_text())
    stage5 = json.loads((Path("benchmarks/results") / STAGE5_REPORT).read_text())
    assert body["baseline"]["recall_at_budget"] == stage5["summaries"]["A"]["recall_at_budget"]
    s_vs_a = body["comparisons"][3]
    assert [s_vs_a["difference"], s_vs_a["ci_low"], s_vs_a["ci_high"]] == stage5["primary"][
        "S_minus_A"
    ]
    c7_table = body["comparisons"][0]
    assert (
        c7_table["difference"]
        == stage4["primary_C7_vs_A"]["table"]["recall_at_budget"]["difference"][0]
    )
    verdicts = [c["verdict"] for c in body["comparisons"]]
    assert verdicts == [
        "inconclusive: not shown to be better than baseline",
        "inconclusive: not shown to be better than baseline",
        "identical to baseline",
        "inconclusive: not shown to be better than baseline",
    ]


def test_evaluation_missing_files(client, ctx, tmp_path):
    ctx.settings.results_dir = tmp_path
    assert client.get("/evaluation").status_code == 404


# ---------------------------------------------------------------- UI serving and citations


def test_built_ui_is_served_from_the_same_origin(ctx, tmp_path):
    ctx.settings.ui_dir = tmp_path / "dist"
    ctx.settings.ui_dir.mkdir()
    (ctx.settings.ui_dir / "index.html").write_text("<html>ui</html>")
    with TestClient(create_app(ctx)) as client:
        assert "ui" in client.get("/").text
        assert client.get("/kbs").json() == []  # API routes still win


def test_citations_carry_the_full_passage(client, ctx):
    kb = make_kb(client)
    text = "The revenue figure grew strongly. " * 12
    client.post(f"/kbs/{kb['id']}/documents", files={"file": ("a.txt", text.encode())})
    ctx.llm.queue(answer="It grew [E1].")
    citation = client.post(f"/kbs/{kb['id']}/query", json={"question": "revenue figure"}).json()[
        "citations"
    ][0]
    assert len(citation["passage"]) > len(citation["snippet"])
    assert citation["passage"].startswith("The revenue figure")


# ---------------------------------------------------------------- separate vector-store process


def _report_environ(queue):
    import os

    queue.put(sorted(os.environ))


def test_store_process_starts_without_api_key_variables(monkeypatch):
    import multiprocessing

    from adaptive_rag.vectorstore.process import _api_keys_removed_from_environ

    monkeypatch.setenv("GEMINI_API_KEY", CANARY)
    monkeypatch.setenv("ADAPTIVE_RAG_OPENAI_API_KEY", CANARY)
    spawn = multiprocessing.get_context("spawn")
    queue = spawn.Queue()
    with _api_keys_removed_from_environ():
        child = spawn.Process(target=_report_environ, args=(queue,))
        child.start()
    names = queue.get(timeout=30)
    child.join()
    assert "GEMINI_API_KEY" not in names and "ADAPTIVE_RAG_OPENAI_API_KEY" not in names
    assert "PATH" in names
    assert os.environ["GEMINI_API_KEY"] == CANARY  # restored in this process


def test_store_process_serves_the_app_and_stops(ctx):
    ctx.store = None
    app = create_app(ctx)
    with TestClient(app) as client:
        process = ctx.store_process._process
        kb = make_kb(client)
        client.post(f"/kbs/{kb['id']}/documents", files={"file": ("a.txt", b"Revenue rose.")})
        ctx.llm.queue(answer="It rose [E1].")
        body = client.post(f"/kbs/{kb['id']}/query", json={"question": "revenue"}).json()
        assert body["status"] == "answered"
        assert client.delete(f"/kbs/{kb['id']}").status_code == 204
    process.join(timeout=10)
    assert not process.is_alive() and ctx.store is None
