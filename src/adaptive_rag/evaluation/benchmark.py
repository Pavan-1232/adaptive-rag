"""Benchmark files: the document manifest and the question sets."""

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

BENCHMARK_DIR = Path("benchmarks")
ANSWERABLE_TYPES = ("factual", "conceptual", "multi_part", "table")
UNANSWERABLE_TYPES = ("near_miss", "out_of_scope")


class ManifestDocument(BaseModel):
    file: str
    set: Literal["dev", "test"]
    title: str
    url: str
    licence: str
    sha256: str

    @property
    def name(self) -> str:
        return Path(self.file).name


class EvidenceOption(BaseModel):
    page: int | None = None
    quote: str = Field(min_length=1)


class Evidence(EvidenceOption):
    """One required fact. Any of its quotes counts, for facts stated in several places."""

    alternatives: list[EvidenceOption] = Field(default_factory=list)


class BenchmarkQuestion(BaseModel):
    id: str
    document: str
    type: Literal["factual", "conceptual", "multi_part", "table", "near_miss", "out_of_scope"]
    question: str = Field(min_length=5)
    answerable: bool
    evidence: list[Evidence] = Field(default_factory=list)
    expected_answer: str | None = None
    notes: str | None = ""
    source: str = "human"

    @model_validator(mode="after")
    def check_consistency(self) -> "BenchmarkQuestion":
        if self.answerable and not self.evidence:
            raise ValueError(f"{self.id}: answerable questions need evidence")
        if self.answerable and self.type not in ANSWERABLE_TYPES:
            raise ValueError(f"{self.id}: type {self.type} is for unanswerable questions")
        if not self.answerable and self.evidence:
            raise ValueError(f"{self.id}: unanswerable questions can't have evidence")
        if not self.answerable and self.type not in UNANSWERABLE_TYPES:
            raise ValueError(f"{self.id}: type {self.type} is for answerable questions")
        return self


def load_manifest(root: Path = BENCHMARK_DIR, split: str | None = None) -> list[ManifestDocument]:
    raw = yaml.safe_load((root / "manifest.yaml").read_text())
    documents = [ManifestDocument(**item) for item in raw["documents"]]
    return [item for item in documents if split is None or item.set == split]


def load_questions(path: Path) -> list[BenchmarkQuestion]:
    raw = yaml.safe_load(path.read_text()) or []
    questions = [BenchmarkQuestion(**item) for item in raw]
    ids = [question.id for question in questions]
    duplicates = {item for item in ids if ids.count(item) > 1}
    if duplicates:
        raise ValueError(f"duplicate question ids: {sorted(duplicates)}")
    return questions


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
