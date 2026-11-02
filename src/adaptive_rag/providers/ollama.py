"""Ollama providers, the local default."""

import time
from typing import Any

import ollama

from .base import EmbeddingInputTooLong, LLMResult, ProviderUnavailable

MAX_TITLE_CHARS = 80


def _unavailable(model: str, exc: Exception) -> ProviderUnavailable:
    return ProviderUnavailable(
        f"Could not use Ollama model '{model}'. Check that Ollama is running and the model "
        f"is pulled. ({type(exc).__name__})"
    )


class OllamaEmbeddings:
    """EmbeddingGemma needs task prompts on every input. Ollama does not add them."""

    id = "ollama"

    def __init__(self, model: str, host: str, batch_size: int = 32):
        self.model = model
        self.batch_size = batch_size
        self.uses_task_prompts = model.startswith("embeddinggemma")
        self.prompt_version = "gemma-task-1" if self.uses_task_prompts else "plain-1"
        self._client = ollama.Client(host=host)
        self._dimensions: int | None = None

    def version(self) -> str:
        """The model digest, which changes if the tag is re-pulled with new weights."""
        try:
            models = self._client.list().models
        except (ConnectionError, ollama.ResponseError) as exc:
            raise _unavailable(self.model, exc) from exc
        for entry in models:
            if entry.model == self.model:
                return entry.digest
        raise ProviderUnavailable(f"Ollama model '{self.model}' is not pulled.")

    def dimensions(self) -> int:
        if self._dimensions is None:
            self._dimensions = len(self.embed_query("dimension probe"))
        return self._dimensions

    def embed_documents(self, texts: list[str], titles: list[str]) -> list[list[float]]:
        prompts = list(texts)
        if self.uses_task_prompts:
            prompts = [
                f"title: {' '.join(title.split())[:MAX_TITLE_CHARS] or 'none'} | text: {text}"
                for text, title in zip(texts, titles, strict=True)
            ]
        vectors: list[list[float]] = []
        for start in range(0, len(prompts), self.batch_size):
            vectors.extend(self._embed(prompts[start : start + self.batch_size]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        prompt = f"task: search result | query: {text}" if self.uses_task_prompts else text
        return self._embed([prompt])[0]

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        try:
            # truncate=False turns Ollama's silent truncation into an error.
            response = self._client.embed(model=self.model, input=inputs, truncate=False)
        except ollama.ResponseError as exc:
            if "context length" in str(exc):
                raise EmbeddingInputTooLong(str(exc)) from exc
            raise _unavailable(self.model, exc) from exc
        except ConnectionError as exc:
            raise _unavailable(self.model, exc) from exc
        return [list(vector) for vector in response.embeddings]


class OllamaLLM:
    id = "ollama"

    def __init__(self, model: str, host: str, num_ctx: int = 8192):
        self.model = model
        self.num_ctx = num_ctx
        self._client = ollama.Client(host=host)

    def generate(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0,
    ) -> LLMResult:
        options: dict[str, Any] = {"num_ctx": self.num_ctx, "temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        started = time.perf_counter()
        try:
            # think=False is required: thinking used up the token limit in the smoke test.
            response = self._client.chat(
                model=self.model, messages=messages, format=schema, think=False, options=options
            )
        except (ConnectionError, ollama.ResponseError) as exc:
            raise _unavailable(self.model, exc) from exc
        return LLMResult(
            text=response.message.content or "",
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
            latency_ms=(time.perf_counter() - started) * 1000,
            finish_reason=response.done_reason,
        )

    def check(self) -> None:
        try:
            self._client.show(self.model)
        except (ConnectionError, ollama.ResponseError) as exc:
            raise _unavailable(self.model, exc) from exc

    def unload(self) -> None:
        try:
            # Requesting an unload of an idle model would first load it.
            if any(entry.model == self.model for entry in self._client.ps().models):
                self._client.generate(model=self.model, keep_alive=0)
        except (ConnectionError, ollama.ResponseError) as exc:
            raise _unavailable(self.model, exc) from exc
