"""Deterministic providers, so unit tests need neither Ollama nor network access."""

import hashlib
import json
import math
import re

from adaptive_rag.providers import EmbeddingInputTooLong, LLMResult


class FakeEmbeddings:
    """Hashed bag of words: texts sharing words get similar vectors."""

    id = "fake"
    model = "fake-embed:1"
    prompt_version = "fake-1"
    DIMENSIONS = 256

    def __init__(self, max_words: int = 100_000, digest: str = "abcdef123456"):
        self.max_words = max_words
        self.digest = digest
        self.fail_with: Exception | None = None

    def version(self) -> str:
        return self.digest

    def dimensions(self) -> int:
        return self.DIMENSIONS

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.DIMENSIONS
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % self.DIMENSIONS
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts, titles):
        if self.fail_with:
            raise self.fail_with
        if any(len(text.split()) > self.max_words for text in texts):
            raise EmbeddingInputTooLong("too long")
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        if self.fail_with:
            raise self.fail_with
        return self._vector(text)


class FakeLLM:
    """Returns queued JSON responses, and records calls for inspection."""

    id = "fake"
    model = "fake-llm:1"

    def __init__(self):
        self.responses: list[str] = []
        self.calls: list[list[dict]] = []
        self.unloads = 0
        self.fail_with: Exception | None = None

    def queue(self, status="answered", answer="The answer [E1].", cited_ids=("E1",)):
        payload = {"status": status, "answer": answer, "cited_ids": list(cited_ids)}
        self.responses.append(json.dumps(payload))

    def generate(self, messages, schema=None, max_tokens=None, temperature=0):
        if self.fail_with:
            raise self.fail_with
        self.calls.append(messages)
        return LLMResult(self.responses.pop(0), 100, 20, 5.0, "stop")

    def check(self):
        if self.fail_with:
            raise self.fail_with

    def unload(self):
        self.unloads += 1
