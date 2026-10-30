"""Provider interfaces. Stage 6 adds OpenAI, Gemini, and Anthropic behind these."""

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderUnavailable(Exception):
    """The provider can't be reached or the model is missing. The message is user-facing."""


class EmbeddingInputTooLong(Exception):
    """An input exceeded the embedding model's limit. It is rejected, never truncated."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    finish_reason: str | None = None


class EmbeddingProvider(Protocol):
    id: str
    model: str
    prompt_version: str

    def version(self) -> str: ...

    def dimensions(self) -> int: ...

    def embed_documents(self, texts: list[str], titles: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class LLMProvider(Protocol):
    id: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0,
    ) -> LLMResult: ...

    def check(self) -> None:
        """Raise ProviderUnavailable if the model can't be used."""
        ...

    def unload(self) -> None: ...
