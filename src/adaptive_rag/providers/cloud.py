"""Cloud answer models (BYOK): OpenAI, Gemini and Anthropic over plain HTTP with httpx.

Security rules, all tested in tests/test_cloud_providers.py:
- The key is sent only in a request header, never in a URL, and it is never logged, traced,
  stored or put in an error message.
- Error messages carry only the provider name, the HTTP status and the provider's error type.
  Provider error text is never passed on: some providers echo part of the key in it.
- Exceptions are raised `from None`, so no httpx exception (which holds the request and its
  headers) is chained onto ours.

Request shapes were checked against each provider's docs on 2026-11-06 (PROGRESS.md, Stage 6).
`temperature` is not sent: Anthropic's 2026-10-21 API version rejects it, Gemini 3.6+ ignores it,
and OpenAI's docs don't say whether its newer models accept it.
"""

import re
import time
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from adaptive_rag.config import Settings

from .base import LLMResult, ProviderUnavailable
from .keys import CLOUD_PROVIDERS, api_key

_ERROR_TYPE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")


class MissingKey(Exception):
    """No API key is configured for the requested provider. The message is user-facing."""


def _split(messages: list[dict[str, str]]) -> tuple[str, str]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    user = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
    return system, user


class _CloudLLM:
    id = ""
    display = ""
    base_url = ""

    def __init__(
        self,
        model: str,
        key: SecretStr,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self._key = key
        self._timeout_s = timeout_s
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"

    # Subclasses define the request and how to read the response.
    def _url(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _body(self, system: str, user: str, schema: dict | None, max_tokens: int | None) -> dict:
        raise NotImplementedError

    def _parse(self, data: dict) -> tuple[str, int | None, int | None, str | None]:
        raise NotImplementedError

    def generate(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float = 0,  # not sent; see the module docstring
    ) -> LLMResult:
        system, user = _split(messages)
        started = time.perf_counter()
        try:
            response = self._client.post(
                self._url(),
                headers=self._headers(),
                json=self._body(system, user, schema, max_tokens),
            )
        except httpx.TimeoutException:
            raise ProviderUnavailable(
                f"{self.display} did not answer within {self._timeout_s:g} s."
            ) from None
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f"Could not reach {self.display} ({type(exc).__name__})."
            ) from None
        if response.status_code >= 400:
            raise ProviderUnavailable(
                f"{self.display} returned HTTP {response.status_code} ({_error_type(response)})."
            ) from None
        try:
            text, input_tokens, output_tokens, finish = self._parse(response.json())
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            raise ProviderUnavailable(
                f"{self.display} returned a response that couldn't be read."
            ) from None
        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
            finish_reason=finish,
        )

    def check(self) -> None:
        """The key was checked when this adapter was built. No network call, no cost."""

    def unload(self) -> None:
        """Nothing is loaded locally."""


def _error_type(response: httpx.Response) -> str:
    """The provider's error type or status name only, never its message text."""
    try:
        error = response.json().get("error")
    except ValueError:
        return "no details"
    if isinstance(error, dict):
        for field in ("type", "status", "code"):
            value = error.get(field)
            if isinstance(value, str) and _ERROR_TYPE.match(value):
                return value
    return "no details"


class OpenAILLM(_CloudLLM):
    id = "openai"
    display = "OpenAI"
    base_url = "https://api.openai.com"

    def _url(self) -> str:
        return f"{self.base_url}/v1/responses"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key.get_secret_value()}"}

    def _body(self, system, user, schema, max_tokens) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if max_tokens is not None:
            body["max_output_tokens"] = max(max_tokens, 16)  # the API's minimum
        if schema is not None:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "schema": schema,
                    "strict": True,
                }
            }
        return body

    def _parse(self, data):
        parts = [
            part
            for item in data.get("output") or []
            if item.get("type") == "message"
            for part in item.get("content") or []
        ]
        # A refusal part has no text, so the answer path treats it as unusable output.
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "output_text")
        incomplete = (data.get("incomplete_details") or {}).get("reason")
        finish = "length" if incomplete == "max_output_tokens" else data.get("status")
        usage = data.get("usage") or {}
        return text, usage.get("input_tokens"), usage.get("output_tokens"), finish


class GeminiLLM(_CloudLLM):
    id = "gemini"
    display = "Gemini"
    base_url = "https://generativelanguage.googleapis.com"

    def _url(self) -> str:
        return f"{self.base_url}/v1beta/models/{quote(self.model, safe='')}:generateContent"

    def _headers(self) -> dict[str, str]:
        # A header, never the ?key= query parameter: URLs end up in logs.
        return {"x-goog-api-key": self._key.get_secret_value()}

    def _body(self, system, user, schema, max_tokens) -> dict:
        config: dict[str, Any] = {}
        if max_tokens is not None:
            config["maxOutputTokens"] = max_tokens
        if schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseJsonSchema"] = schema
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": config,
        }

    def _parse(self, data):
        candidates = data.get("candidates") or []
        candidate = candidates[0] if candidates else {}
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        finish = candidate.get("finishReason")
        usage = data.get("usageMetadata") or {}
        return (
            text,
            usage.get("promptTokenCount"),
            usage.get("candidatesTokenCount"),
            "length" if finish == "MAX_TOKENS" else finish,
        )


class AnthropicLLM(_CloudLLM):
    id = "anthropic"
    display = "Anthropic"
    base_url = "https://api.anthropic.com"
    api_version = "2026-10-21"

    def _url(self) -> str:
        return f"{self.base_url}/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._key.get_secret_value(), "anthropic-version": self.api_version}

    def _body(self, system, user, schema, max_tokens) -> dict:
        # Low effort: answering from given evidence is a simple task, and thinking tokens count
        # against max_tokens.
        output_config: dict[str, Any] = {"effort": "low"}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        return {
            "model": self.model,
            "max_tokens": max_tokens or 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }

    def _parse(self, data):
        text = "".join(
            block.get("text", "")
            for block in data.get("content") or []
            if block.get("type") == "text"
        )
        stop = data.get("stop_reason")
        if stop == "refusal":
            text = ""  # a refusal is not an answer; the answer path reports it as unusable
        usage = data.get("usage") or {}
        return (
            text,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            "length" if stop == "max_tokens" else stop,
        )


ADAPTERS: dict[str, type[_CloudLLM]] = {
    "openai": OpenAILLM,
    "gemini": GeminiLLM,
    "anthropic": AnthropicLLM,
}
assert set(ADAPTERS) == set(CLOUD_PROVIDERS)


def cloud_llm(
    settings: Settings, provider: str, transport: httpx.BaseTransport | None = None
) -> _CloudLLM:
    """Build the adapter for a provider with the user's key, or raise MissingKey."""
    adapter = ADAPTERS[provider]
    key = api_key(settings, provider)
    if key is None:
        env = f"{provider.upper()}_API_KEY"
        raise MissingKey(
            f"No API key is configured for {adapter.display}. Set {env} in .env to use it."
        )
    model = getattr(settings, f"{provider}_model")
    return adapter(model, key, settings.cloud_timeout_s, transport=transport)
