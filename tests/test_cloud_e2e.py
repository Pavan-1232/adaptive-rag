"""Real calls to cloud providers with the user's own keys. Off by default; they cost money.

Run with: pytest -m cloud. A provider whose key isn't set is skipped. These confirm what the docs
check couldn't settle (PROGRESS.md, Stage 6): structured output on each default model, and
Gemini's key in the x-goog-api-key header.
"""

import json

import pytest

from adaptive_rag.answering.prompts import ANSWER_SCHEMA
from adaptive_rag.config import Settings
from adaptive_rag.providers.cloud import cloud_llm
from adaptive_rag.providers.keys import CLOUD_PROVIDERS, api_key

pytestmark = pytest.mark.cloud

MESSAGES = [
    {
        "role": "system",
        "content": "Answer only from the evidence. Reply as JSON with status, answer, cited_ids.",
    },
    {
        "role": "user",
        "content": '<evidence id="E1">Revenue grew 8% in 2024.</evidence>\n'
        "Question: How much did revenue grow in 2024?",
    },
]


@pytest.mark.parametrize("provider", CLOUD_PROVIDERS)
def test_real_structured_answer(provider):
    settings = Settings()
    if api_key(settings, provider) is None:
        pytest.skip(f"no {provider} key set")
    result = cloud_llm(settings, provider).generate(MESSAGES, ANSWER_SCHEMA, max_tokens=1024)
    output = json.loads(result.text)
    assert set(output) == {"status", "answer", "cited_ids"}
    assert output["status"] in ("answered", "partial", "insufficient")
    assert result.input_tokens and result.output_tokens
