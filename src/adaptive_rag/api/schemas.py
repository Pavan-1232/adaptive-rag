"""Request and response models for the HTTP API."""

import json
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class KnowledgeBaseOut(BaseModel):
    id: int
    name: str
    embedding_provider: str
    embedding_model: str
    embedding_version: str
    embedding_dimensions: int
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "KnowledgeBaseOut":
        return cls(**{name: row[name] for name in cls.model_fields})


class DocumentOut(BaseModel):
    id: int
    kb_id: int
    filename: str
    format: str
    sha256: str
    size_bytes: int
    version: int
    status: str
    error: str | None
    warnings: list[str]
    locator_kind: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DocumentOut":
        fields = {name: row[name] for name in cls.model_fields if name != "warnings"}
        return cls(warnings=json.loads(row["warnings"]), **fields)


class UploadOut(BaseModel):
    document: DocumentOut
    job_id: int | None
    duplicate: bool


class JobOut(BaseModel):
    id: int
    document_id: int | None
    kind: str
    status: str
    error: str | None
    created_at: str
    updated_at: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class CitationOut(BaseModel):
    id: str
    document_id: int
    filename: str
    locator_kind: str
    locator_start: int
    locator_end: int
    section_heading: str | None
    label: str
    snippet: str
    score: float
    source: str


class QueryResponse(BaseModel):
    status: Literal["answered", "partial", "insufficient"]
    answer: str
    citations: list[CitationOut]
    warnings: list[str]
    input_tokens: int | None
    output_tokens: int | None
    timings_ms: dict[str, float]
    trace_id: int


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    embedding_model: bool
    llm_model: bool
