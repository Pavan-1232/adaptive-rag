"""The FastAPI application. Single-user and local: one worker, bound to 127.0.0.1."""

import json
import tempfile
import threading
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers

from adaptive_rag.answering import CloudNotAllowed, GenerationFailed, answer_question
from adaptive_rag.config import Settings
from adaptive_rag.context import AppContext
from adaptive_rag.db import migrate
from adaptive_rag.evaluation.summary import evaluation_summary
from adaptive_rag.ingest import (
    VersionInProgress,
    delete_document,
    delete_knowledge_base,
    register_upload,
    repair_on_startup,
    run_ingest_job,
)
from adaptive_rag.knowledge_bases import (
    EmbeddingModelMismatch,
    KnowledgeBaseExists,
    create_knowledge_base,
)
from adaptive_rag.loaders import UploadRejected
from adaptive_rag.providers import OllamaEmbeddings, OllamaLLM, ProviderUnavailable
from adaptive_rag.providers.cloud import MissingKey
from adaptive_rag.providers.keys import (
    CLOUD_PROVIDERS,
    InvalidKey,
    KeychainError,
    api_key,
    key_source,
    remove_key,
    store_key,
)
from adaptive_rag.vectorstore.process import start_store_process

from .schemas import (
    CitationOut,
    DocumentOut,
    HealthOut,
    JobOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    QueryRequest,
    QueryResponse,
    UploadOut,
)


def build_context(settings: Settings) -> AppContext:
    return AppContext(
        settings=settings,
        embedder=OllamaEmbeddings(
            settings.embedding_model, settings.ollama_host, settings.embedding_batch_size
        ),
        llm=OllamaLLM(settings.llm_model, settings.ollama_host, settings.num_ctx),
        store=None,  # started in its own process by the app's lifespan
    )


def _run_jobs(ctx: AppContext, job_ids: list[int]) -> None:
    for job_id in job_ids:
        run_ingest_job(ctx, job_id)


def create_app(ctx: AppContext | None = None) -> FastAPI:
    context = ctx or build_context(Settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Iterator[None]:
        owns_store = context.store is None
        if owns_store:
            context.store_process, context.store = start_store_process(context.settings.chroma_dir)
        try:
            with context.db() as conn:
                migrate(conn)
            job_ids = repair_on_startup(context)
            if job_ids:
                threading.Thread(target=_run_jobs, args=(context, job_ids), daemon=True).start()
            yield
        finally:
            if owns_store:
                context.store_process.shutdown()
                context.store_process = context.store = None

    app = FastAPI(title="Adaptive RAG", version="0.1.0", lifespan=lifespan)
    app.state.context = context
    app.add_middleware(LocalOnly, allowed_hosts=context.settings.allowed_hosts)
    _add_error_handlers(app)
    _add_routes(app)
    ui_dir = context.settings.ui_dir
    if (ui_dir / "index.html").is_file():
        # Mounted last, so API routes take precedence.
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return app


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class LocalOnly:
    """Defence against other websites reaching this local server through the user's browser.

    - Host must be an allowed name (blocks DNS rebinding: a hostile domain resolving to 127.0.0.1).
    - Changing requests must come from this app's own origin (blocks cross-site form posts and
      fetches to localhost). Browsers always send Origin on those; a request with no Origin and no
      Sec-Fetch-Site is a non-browser client such as curl, which no website can drive.
    - The UI calls /api/...; the prefix is stripped so the routes stay at their existing paths.
    """

    def __init__(self, app, allowed_hosts: list[str]):
        self.app = app
        self.allowed_hosts = set(allowed_hosts)

    def _host_allowed(self, host: str) -> bool:
        name, _, port = host.rpartition(":") if ":" in host else (host, "", "")
        return name in self.allowed_hosts and (port == "" or port.isdigit())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        if not self._host_allowed(host):
            response = JSONResponse({"detail": "Requests must be addressed to localhost."}, 400)
            return await response(scope, receive, send)
        if scope["method"] not in _SAFE_METHODS:
            origin = headers.get("origin")
            site = headers.get("sec-fetch-site")
            if (origin is not None and origin != f"http://{host}") or site in (
                "cross-site",
                "same-site",
            ):
                response = JSONResponse({"detail": "Cross-site requests are not allowed."}, 403)
                return await response(scope, receive, send)
        path = scope["path"]
        if path == "/api" or path.startswith("/api/"):
            scope = dict(scope, path=path[4:] or "/")
        return await self.app(scope, receive, send)


def _add_error_handlers(app: FastAPI) -> None:
    errors = {
        ProviderUnavailable: 503,
        EmbeddingModelMismatch: 409,
        KnowledgeBaseExists: 409,
        VersionInProgress: 409,
        UploadRejected: 400,
        GenerationFailed: 502,
        CloudNotAllowed: 403,
        MissingKey: 400,
        InvalidKey: 400,
        KeychainError: 503,
    }
    messages = {
        KnowledgeBaseExists: "A knowledge base with this name already exists.",
        VersionInProgress: "An earlier version of this file is still being indexed.",
    }

    for error_type, status_code in errors.items():

        def handler(_: Request, exc: Exception, code=status_code, kind=error_type) -> JSONResponse:
            return JSONResponse(
                status_code=code, content={"detail": messages.get(kind) or str(exc)}
            )

        app.add_exception_handler(error_type, handler)


def _get_context(request: Request) -> AppContext:
    return request.app.state.context


def _get_kb(kb_id: int, ctx: AppContext = Depends(_get_context)):  # noqa: B008
    with ctx.db() as conn:
        kb = conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)).fetchone()
    if kb is None:
        raise HTTPException(404, "Knowledge base not found.")
    return kb


def _save_upload(file: UploadFile, destination: Path, max_bytes: int) -> None:
    """Stream to disk and stop early, so a huge upload can't fill memory."""
    written = 0
    with destination.open("wb") as output:
        while block := file.file.read(1024 * 1024):
            written += len(block)
            if written > max_bytes:
                limit = max_bytes // (1024 * 1024)
                raise HTTPException(413, f"This file is larger than the {limit} MB limit.")
            output.write(block)


def _add_routes(app: FastAPI) -> None:
    context = Depends(_get_context)
    knowledge_base = Depends(_get_kb)

    @app.get("/health", response_model=HealthOut)
    def health(ctx: AppContext = context) -> HealthOut:
        def works(check) -> bool:
            try:
                check()
                return True
            except ProviderUnavailable:
                return False

        with ctx.db() as conn:
            database = conn.execute("SELECT 1").fetchone() is not None
        embedding = works(ctx.embedder.version)
        llm = works(ctx.llm.check)
        healthy = database and embedding and llm
        return HealthOut(
            status="ok" if healthy else "degraded",
            database=database,
            embedding_model=embedding,
            llm_model=llm,
            cloud_keys={p: api_key(ctx.settings, p) is not None for p in CLOUD_PROVIDERS},
        )

    @app.post("/kbs", response_model=KnowledgeBaseOut, status_code=201)
    def create_kb(body: KnowledgeBaseCreate, ctx: AppContext = context) -> KnowledgeBaseOut:
        return KnowledgeBaseOut.from_row(create_knowledge_base(ctx, body.name, body.allow_cloud))

    @app.patch("/kbs/{kb_id}", response_model=KnowledgeBaseOut)
    def update_kb(
        body: KnowledgeBaseUpdate, kb=knowledge_base, ctx: AppContext = context
    ) -> KnowledgeBaseOut:
        with ctx.db() as conn:
            conn.execute(
                "UPDATE knowledge_bases SET allow_cloud = ? WHERE id = ?",
                (int(body.allow_cloud), kb["id"]),
            )
            row = conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb["id"],)).fetchone()
        return KnowledgeBaseOut.from_row(row)

    @app.delete("/kbs/{kb_id}", status_code=204)
    def delete_kb(kb=knowledge_base, ctx: AppContext = context) -> None:
        with ctx.db() as conn:
            busy = conn.execute(
                "SELECT 1 FROM documents WHERE kb_id = ? AND status IN ('pending', 'indexing')",
                (kb["id"],),
            ).fetchone()
        if busy:
            raise HTTPException(409, "A document in this knowledge base is still being indexed.")
        delete_knowledge_base(ctx, kb)

    @app.get("/kbs", response_model=list[KnowledgeBaseOut])
    def list_kbs(ctx: AppContext = context) -> list[KnowledgeBaseOut]:
        with ctx.db() as conn:
            rows = conn.execute("SELECT * FROM knowledge_bases ORDER BY id").fetchall()
        return [KnowledgeBaseOut.from_row(row) for row in rows]

    @app.post("/kbs/{kb_id}/documents", response_model=UploadOut, status_code=202)
    def upload_document(
        file: UploadFile,
        background: BackgroundTasks,
        kb=knowledge_base,
        ctx: AppContext = context,
    ) -> UploadOut:
        filename = file.filename or "upload"
        ctx.settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ctx.settings.data_dir) as temp_dir:
            temp_path = Path(temp_dir) / "upload"
            _save_upload(file, temp_path, ctx.settings.max_upload_bytes)
            document, job_id, duplicate = register_upload(ctx, kb, temp_path, filename)
        if job_id is not None:
            background.add_task(run_ingest_job, ctx, job_id)
        return UploadOut(
            document=DocumentOut.from_row(document), job_id=job_id, duplicate=duplicate
        )

    @app.get("/kbs/{kb_id}/documents", response_model=list[DocumentOut])
    def list_documents(kb=knowledge_base, ctx: AppContext = context) -> list[DocumentOut]:
        with ctx.db() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE kb_id = ? AND status != 'superseded' ORDER BY id",
                (kb["id"],),
            ).fetchall()
        return [DocumentOut.from_row(row) for row in rows]

    @app.delete("/documents/{document_id}", status_code=204)
    def remove_document(document_id: int, ctx: AppContext = context) -> None:
        with ctx.db() as conn:
            row = conn.execute(
                "SELECT status FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "Document not found.")
        if row["status"] in ("pending", "indexing"):
            raise HTTPException(409, "This document is still being indexed.")
        delete_document(ctx, document_id)

    @app.get("/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: int, ctx: AppContext = context) -> JobOut:
        with ctx.db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Job not found.")
        return JobOut(**{name: row[name] for name in JobOut.model_fields})

    @app.post("/kbs/{kb_id}/query", response_model=QueryResponse)
    def query(body: QueryRequest, kb=knowledge_base, ctx: AppContext = context) -> QueryResponse:
        result = answer_question(ctx, kb, body.question, body.provider)
        return QueryResponse(
            status=result.status,
            answer=result.answer,
            citations=[CitationOut(**asdict(citation)) for citation in result.citations],
            warnings=result.warnings,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            timings_ms=result.timings_ms,
            trace_id=result.trace_id,
            provider=body.provider,
        )

    @app.get("/keys")
    def list_keys(ctx: AppContext = context) -> dict[str, str]:
        """Where each provider's key comes from. Never the key, or any part of it."""
        return {provider: key_source(ctx.settings, provider) for provider in CLOUD_PROVIDERS}

    # The body is parsed here, not by a Pydantic model, because FastAPI's default 422 response
    # repeats the submitted input, which would echo the key. Every error message here is fixed.
    @app.put("/keys/{provider}", status_code=204)
    async def put_key(provider: str, request: Request) -> Response:
        if provider not in CLOUD_PROVIDERS:
            raise HTTPException(404, "Unknown provider.")
        body = await request.body()
        if len(body) > 4096:
            raise HTTPException(413, "The request is too large.")
        try:
            key = json.loads(body)["key"]
        except (ValueError, KeyError, TypeError):
            key = None
        if not isinstance(key, str):
            raise HTTPException(400, 'Send JSON in the form {"key": "..."}.')
        await run_in_threadpool(store_key, provider, key)
        return Response(status_code=204)

    @app.delete("/keys/{provider}", status_code=204)
    def delete_key(provider: str) -> None:
        if provider not in CLOUD_PROVIDERS:
            raise HTTPException(404, "Unknown provider.")
        remove_key(provider)

    @app.get("/evaluation")
    def evaluation(ctx: AppContext = context) -> dict:
        try:
            return evaluation_summary(ctx.settings.results_dir)
        except FileNotFoundError:
            raise HTTPException(404, "Evaluation results not found.") from None
