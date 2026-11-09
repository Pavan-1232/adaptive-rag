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


# Real-use failures (PROGRESS.md, 2026-11-09). Made-up questions in the layout of a CA question
# bank (source label per question, no answer key) and a study-material unit (separate key).
BANK_MCQS = (
    "CHAPTER 1 Basics of Indirect Tax\n"
    "01 Source: Study Unit 1, Practice Q.1\n"
    "In India, meetings of the GST Council are chaired by\n"
    "(a) the Prime Minister\n(b) the Union Finance Minister\n(c) the RBI Governor\n"
    "(d) the Chief Justice of India\n"
    "02 Source: Study Unit 1, Practice Q.2\n"
    "A good tax system\n(a) Raises revenue fairly.\n(b) Is simple to comply with.\n"
    "(c) Both (a) and (b).\n(d) Changes every month.\n"
)
BANK_EXPLANATORY = (
    "07 Source: Study Unit 4, Practice Q.7\n"
    "Harbor Foods Ltd. has borrowed heavily from Lakeview Bank Ltd., a commercial bank that lends "
    "to it on normal terms. Lakeview Bank holds no shares in Harbor Foods and has no say in its "
    "decisions. Is Lakeview Bank a related party of Harbor Foods under AS 18?\n"
    "(a) Yes, any lender with a large loan outstanding is automatically a related party.\n"
    "(b) Yes, but only if the loan exceeds half of total borrowings.\n"
    "(c) No - AS 18 states that providers of finance, in the course of their business with an "
    "enterprise, are not related parties merely because of those dealings; without control or "
    "significant influence, lending alone does not create a related party relationship.\n"
    "(d) No, because AS 18 applies only to individuals.\n"
)
UNIT_QUESTIONS = (
    "STUDY UNIT 4\nTEST YOUR KNOWLEDGE\nMultiple Choice Questions\n"
    "1. Vega Ltd. paid income tax of 12,000 on its operating profit and cannot link it to any "
    "investing or financing item. Under which activity is it shown in the cash flow statement?\n"
    "(a) Operating activities\n(b) Investing activities\n(c) Financing activities\n"
    "(d) Not shown\n"
    "2. Interest received by a manufacturing company on a fixed deposit is shown as\n"
    "(a) operating cash inflow\n(b) investing cash inflow\n(c) financing cash inflow\n"
    "(d) cash equivalent\n"
)
UNIT_KEY = (
    "STUDY UNIT 4\nANSWERS/HINTS\nAnswers to the Multiple Choice Questions\n"
    "1. (a) 2. (b) 3. (c) 4. (d) 5. (a)\n6 (b) 7 (c)\nAnswers to the Theoretical Questions\n"
    "8. A cash flow statement shows where cash came from and how it was used in a period.\n"
)
CSR = (
    "Q14. Which section of the Companies Act, 2013 deals with Corporate Social Responsibility?\n"
    "(a) Section 135\n(b) Section 149\n(c) Section 186\n(d) Section 188\n"
)
NO_KEY_CASES = {
    "explanatory_option": (
        "Is Lakeview Bank a related party of Harbor Foods under AS 18 because of the loan?",
        [("question_bank.pdf", 35, BANK_EXPLANATORY)],
    ),
    "model_knows_answer": (
        "Who chairs the GST Council, according to the first MCQ?",
        [("question_bank.pdf", 3, BANK_MCQS)],
    ),
    "content_question": (
        "Which section of the Companies Act, 2013 deals with CSR?",
        [("question_bank.pdf", 3, CSR)],
    ),
}


def gemini_answer(question, passages):
    from adaptive_rag.answering.prompts import build_messages
    from adaptive_rag.retrieval import RetrievedChunk

    settings = Settings()
    if api_key(settings, "gemini") is None:
        pytest.skip("no gemini key set")
    chunks = [
        RetrievedChunk(f"1-{i}", 1, name, i, text, 200, 0.8, "page", page, page, None)
        for i, (name, page, text) in enumerate(passages)
    ]
    messages = build_messages(question, chunks)
    result = cloud_llm(settings, "gemini").generate(messages, ANSWER_SCHEMA, max_tokens=1024)
    output = json.loads(result.text)
    print(output)
    return output


@pytest.mark.parametrize("case", NO_KEY_CASES)
def test_gemini_does_not_pick_an_option_without_answer_key(case):
    """One real call each. The model may know the answer; the document doesn't state it."""
    output = gemini_answer(*NO_KEY_CASES[case])
    assert output["status"] != "answered"
    assert "not given" in output["answer"] or "isn't given" in output["answer"]


def test_gemini_uses_a_separate_answer_key():
    """The opposite case: the key is a separate table pages later, so the rule must not refuse."""
    question = (
        "Can you give me the solution to question 1 in Study Unit 4, the Vega Ltd. income tax "
        "question? Give me the right answer."
    )
    output = gemini_answer(
        question, [("study_unit_4.pdf", 18, UNIT_QUESTIONS), ("study_unit_4.pdf", 23, UNIT_KEY)]
    )
    assert output["status"] == "answered"
    assert "operating" in output["answer"].lower() and "given" not in output["answer"]
    assert {"E1", "E2"} <= set(output["cited_ids"])
