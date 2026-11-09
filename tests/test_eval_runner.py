import json

import pytest
import yaml

from adaptive_rag.evaluation.benchmark import BenchmarkQuestion, ManifestDocument
from adaptive_rag.evaluation.calibration import choose_floor, evaluate_floor, sweep
from adaptive_rag.evaluation.judge import compare_to_reference, judge_answer, quote_backs_claim
from adaptive_rag.evaluation.leakage import shared_documents
from adaptive_rag.evaluation.report import render_markdown, summarize
from adaptive_rag.evaluation.runner import (
    build_index,
    is_complete,
    load_partial,
    resume_conflicts,
    run_benchmark,
    save_results,
)
from fakes import FakeEmbeddings, FakeLLM


class JudgeLLM(FakeLLM):
    model = "fake-judge:1"

    def __init__(
        self, supported=True, addresses=True, raw=None, quote="Revenue grew", verdict="agrees"
    ):
        super().__init__()
        self.quote = quote
        self.verdict = verdict
        self.raw = raw
        self.supported = supported
        self.addresses = addresses

    def generate(self, messages, schema=None, max_tokens=None, temperature=0):
        from adaptive_rag.providers import LLMResult

        self.calls.append(messages)
        if "verdict" in schema["properties"]:
            return LLMResult(self.raw or json.dumps({"verdict": self.verdict}), 10, 5, 1.0, "stop")
        claim = {"claim": "c", "evidence_quote": self.quote, "supported": self.supported}
        text = self.raw or json.dumps({"claims": [claim], "addresses_question": self.addresses})
        return LLMResult(text, 10, 5, 1.0, "stop")


GOOD = "Revenue grew eight percent because subscriptions expanded."
OTHER = "The office canteen serves lunch at noon every working day."


@pytest.fixture
def indexed(settings, tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "report.txt").write_text(f"{GOOD}\n")
    (root / "canteen.txt").write_text(f"{OTHER}\n")
    documents = [
        ManifestDocument(file=name, set="dev", title=name, url="u", licence="l", sha256="s")
        for name in ("report.txt", "canteen.txt")
    ]
    return build_index(settings, FakeEmbeddings(), FakeLLM(), documents, root, "benchmark-dev")


def answerable(question="Why did revenue grow?", document="report.txt", quote=GOOD):
    return BenchmarkQuestion(
        id="q1",
        document=document,
        type="factual",
        question=question,
        answerable=True,
        evidence=[{"quote": quote}],
    )


def near_miss():
    return BenchmarkQuestion(
        id="u1",
        document="report.txt",
        type="near_miss",
        question="Who approved the revenue budget?",
        answerable=False,
    )


def test_retrieval_metrics_on_a_known_document(indexed):
    ctx, kb, docs = indexed
    result = run_benchmark(ctx, kb, docs, [answerable()], answers=False)[0]
    assert result.recall_at_5 == 1.0 and result.hit_at_5 == 1.0
    assert result.reciprocal_rank == 1.0 and result.recall_at_budget == 1.0
    assert result.status is None


def test_rebuilding_the_index_reuses_it(settings, indexed, tmp_path):
    ctx, kb, docs = indexed
    documents = [
        ManifestDocument(file="report.txt", set="dev", title="r", url="u", licence="l", sha256="s")
    ]
    _, kb_again, docs_again = build_index(
        settings, ctx.embedder, ctx.llm, documents, tmp_path / "docs", "benchmark-dev"
    )
    assert kb_again["id"] == kb["id"]
    assert docs_again["report.txt"]["id"] == docs["report.txt"]["id"]


def test_missing_quote_stops_the_run(indexed):
    ctx, kb, docs = indexed
    with pytest.raises(ValueError, match="not found"):
        run_benchmark(ctx, kb, docs, [answerable(quote="Never written anywhere")], answers=False)


def test_answer_citing_evidence_counts_as_on_evidence(indexed):
    ctx, kb, docs = indexed
    # Fake retrieval ranks report.txt first for this question, so it becomes E1.
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    result = run_benchmark(ctx, kb, docs, [answerable(question="revenue grew eight percent")])[0]
    assert result.status == "answered"
    assert result.citation_on_evidence is True and result.citation_precision == 1.0


def test_answered_with_wrong_citation_is_wrong_focus(indexed):
    ctx, kb, docs = indexed
    ctx.llm.queue(answer="Lunch is at noon [E2].", cited_ids=["E2"])
    results = run_benchmark(ctx, kb, docs, [answerable(question="revenue grew eight percent")])
    assert results[0].citation_on_evidence is False
    assert summarize([vars(results[0])])["wrong_focus_by_citation"] == 1


def test_gate_is_off_during_runs_and_restored_after(indexed):
    ctx, kb, docs = indexed
    ctx.settings.score_floor = 0.99
    ctx.llm.queue(status="insufficient", answer="", cited_ids=[])
    run_benchmark(ctx, kb, docs, [near_miss()])
    assert len(ctx.llm.calls) == 1
    assert ctx.settings.score_floor == 0.99


def test_judge_scores_faithfulness_and_focus(indexed):
    ctx, kb, docs = indexed
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    judge = JudgeLLM(supported=False, addresses=False)
    result = run_benchmark(
        ctx, kb, docs, [answerable(question="revenue grew eight percent")], judge=judge
    )[0]
    assert result.faithfulness == 0.0 and result.addresses_question is False
    assert ctx.llm.unloads >= 1 and judge.unloads == 1


def test_faithfulness_needs_the_llm_and_the_code_check_to_agree(indexed):
    ctx, kb, docs = indexed
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    judge = JudgeLLM(quote="Words the evidence never contained")
    result = run_benchmark(
        ctx, kb, docs, [answerable(question="revenue grew eight percent")], judge=judge
    )[0]
    assert result.faithfulness == 0.0
    assert result.judge_claims[0]["supported"] is True
    assert result.judge_claims[0]["verified"] is False


def test_gold_comparison_is_recorded_for_answerable_questions(indexed):
    ctx, kb, docs = indexed
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    judge = JudgeLLM(verdict="conflicts")
    result = run_benchmark(
        ctx, kb, docs, [answerable(question="revenue grew eight percent")], judge=judge
    )[0]
    assert result.reference_verdict == "conflicts"
    assert summarize([vars(result)])["reference_conflicts"] == 1


def test_unusable_gold_comparison_is_not_invented():
    assert compare_to_reference(JudgeLLM(raw="garbage"), "q", "a", "r") is None


@pytest.mark.parametrize(
    ("claim", "quote", "expected"),
    [
        ("Liabilities were $48,390 million [E2].", "Total liabilities 48,390 43,009", True),
        ("Liabilities were $58,390 million.", "Total liabilities 48,390 43,009", False),
        ("In the year ended December 31, 2024, notes added 1.", "Convertible notes 1 2 3", True),
        ("Liabilities were high.", "A quote that is not in the evidence", False),
        ("Liabilities were high.", "", False),
        ("Liabilities and notes.", "Total liabilities 48,390 [...] Convertible notes 1", True),
        ("Liabilities and notes.", "Total liabilities 48,390 [...] Preferred stock 7", False),
        ("Liabilities were 48,390.", "Total liabilities, 48,390 43,009", True),
        ("Notes added 3.", "Convertible notes 1", True),
    ],
)
def test_code_check_on_quotes_and_numbers(claim, quote, expected):
    evidence = ["Total liabilities 48,390 43,009\nConvertible notes 1 2 3"]
    assert quote_backs_claim(claim, quote, evidence) is expected


def test_any_listed_evidence_location_counts(indexed):
    ctx, kb, docs = indexed
    question = BenchmarkQuestion(
        id="q1",
        document="report.txt",
        type="factual",
        question="revenue grew eight percent",
        answerable=True,
        evidence=[{"quote": "because subscriptions", "alternatives": [{"quote": GOOD}]}],
    )
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    result = run_benchmark(ctx, kb, docs, [question])[0]
    assert result.hit_at_5 == 1.0 and result.recall_at_5 == 1.0
    assert result.citation_on_evidence is True


def test_missing_alternative_quote_stops_the_run(indexed):
    ctx, kb, docs = indexed
    question = BenchmarkQuestion(
        id="q1",
        document="report.txt",
        type="factual",
        question="Why did revenue grow?",
        answerable=True,
        evidence=[{"quote": GOOD, "alternatives": [{"quote": "Never written anywhere"}]}],
    )
    with pytest.raises(ValueError, match="not found"):
        run_benchmark(ctx, kb, docs, [question], answers=False)


def test_judge_not_asked_about_refusals(indexed):
    ctx, kb, docs = indexed
    ctx.llm.queue(status="insufficient", answer="", cited_ids=[])
    judge = JudgeLLM()
    run_benchmark(ctx, kb, docs, [near_miss()], judge=judge)
    assert judge.calls == []


def test_unusable_judge_output_is_not_invented():
    assert judge_answer(JudgeLLM(raw="garbage"), "q", "a", ["e"]) is None


def test_judge_with_no_claims_has_no_faithfulness_score():
    raw = json.dumps({"claims": [], "addresses_question": True})
    assert judge_answer(JudgeLLM(raw=raw), "q", "a", ["e"]).faithfulness is None


def records():
    def record(identifier, answerable_flag, kind, score, status):
        return {
            "id": identifier,
            "answerable": answerable_flag,
            "type": kind,
            "top_score": score,
            "status": status,
        }

    return [
        record("a1", True, "factual", 0.6, "answered"),
        record("a2", True, "factual", 0.5, "answered"),
        record("a3", True, "factual", 0.4, "answered"),
        record("a4", True, "factual", 0.3, "answered"),
        record("n1", False, "near_miss", 0.45, "answered"),
        record("n2", False, "near_miss", 0.35, "insufficient"),
        record("o1", False, "out_of_scope", 0.1, "insufficient"),
    ]


def test_floor_replay_hand_calculated():
    outcome = evaluate_floor(records(), 0.4)
    assert outcome.answerable_blocked == 0.25  # a4 is blocked.
    assert outcome.gate_refused_near_miss == 0.5  # n2 only.
    assert outcome.gate_refused_out_of_scope == 1.0
    assert outcome.system_refused_unanswerable == 2 / 3  # n1 still gets through.
    assert outcome.false_answers == 1
    assert outcome.llm_calls_saved == 3 / 7


def test_choose_floor_respects_the_blocked_limit():
    assert choose_floor(sweep(records()), max_blocked=0.0).floor == 0.3
    assert choose_floor(sweep(records()), max_blocked=0.25).floor == 0.4


def test_summary_counts_and_report_never_invent_numbers():
    rows = [{**r, "recall_at_budget": None} for r in records()]
    summary = summarize(rows)
    assert summary["answered"] == 4 and summary["false_answers"] == 1
    assert summary["recall_at_budget"] is None
    text = render_markdown({"system": "A", "set": "dev"}, summary)
    assert "not measured" in text


def test_saved_results_round_trip(indexed, tmp_path):
    ctx, kb, docs = indexed
    results = run_benchmark(ctx, kb, docs, [answerable()], answers=False)
    path = tmp_path / "r" / "out.json"
    save_results(path, {"set": "dev"}, results)
    assert json.loads(path.read_text())["results"][0]["id"] == "q1"


def test_leakage_check_catches_a_test_document_in_dev(tmp_path):
    root = tmp_path
    (root / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "documents": [
                    {
                        "file": "dev/a.pdf",
                        "set": "dev",
                        "title": "a",
                        "url": "u",
                        "licence": "l",
                        "sha256": "same",
                    },
                    {
                        "file": "test/b.pdf",
                        "set": "test",
                        "title": "b",
                        "url": "u",
                        "licence": "l",
                        "sha256": "same",
                    },
                ]
            }
        )
    )
    assert shared_documents(root)


def test_real_manifest_has_no_leakage():
    assert shared_documents() == []


def two_questions():
    second = answerable(question="Why did revenue grow so much?")
    second = BenchmarkQuestion(**{**second.model_dump(), "id": "q2"})
    return [answerable(question="revenue grew eight percent"), second]


def test_progress_is_saved_after_every_question_and_judge_call(indexed):
    ctx, kb, docs = indexed
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    saves = []
    run_benchmark(
        ctx,
        kb,
        docs,
        two_questions(),
        judge=JudgeLLM(),
        on_save=lambda r: saves.append([(x.id, x.status, x.judged) for x in r]),
    )
    assert saves[0] == [("q1", "answered", False)]
    assert saves[1] == [("q1", "answered", False), ("q2", "answered", False)]
    assert saves[-1] == [("q1", "answered", True), ("q2", "answered", True)]
    assert len(saves) == 4


def test_resume_skips_answered_questions_and_judges_only_the_rest(indexed, tmp_path):
    ctx, kb, docs = indexed
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    path = tmp_path / "run.json"
    first = run_benchmark(
        ctx,
        kb,
        docs,
        two_questions()[:1],
        on_save=lambda r: save_results(path, {"set": "dev"}, r, complete=False),
    )
    assert not first[0].judged
    _, done = load_partial(path)

    ctx.llm.calls.clear()
    ctx.llm.queue(answer="Subscriptions expanded [E1].")
    judge = JudgeLLM()
    results = run_benchmark(ctx, kb, docs, two_questions(), judge=judge, done=done)
    assert len(ctx.llm.calls) == 1  # Only q2 was answered.
    assert [r.id for r in results] == ["q1", "q2"]
    assert all(r.judged for r in results)
    assert results[0].faithfulness == 1.0  # q1 was judged from rebuilt evidence.

    judge.calls.clear()
    again = run_benchmark(
        ctx, kb, docs, two_questions(), judge=judge, done={r.id: r for r in results}
    )
    assert judge.calls == [] and len(again) == 2


def test_partial_files_are_marked_and_old_files_count_as_complete(tmp_path):
    path = tmp_path / "run.json"
    save_results(path, {"set": "dev"}, [], complete=False)
    assert not is_complete(json.loads(path.read_text()))
    assert not path.with_suffix(".tmp").exists()
    assert is_complete({"metadata": {"set": "dev"}, "results": []})


def test_resume_refuses_a_different_setup():
    saved = {"embedding_model": "a", "judge_prompt": "audit-1", "questions_sha256": "x"}
    assert resume_conflicts(saved, {**saved, "questions_sha256": "y"}) == ["questions_sha256"]
    assert resume_conflicts(saved, dict(saved)) == []


def test_evaluation_settings_ignore_a_personal_env(tmp_path, monkeypatch):
    """A local .env with hybrid on once leaked into dev runs (PROGRESS.md, 2026-11-09)."""
    import argparse

    import adaptive_rag.evaluation.__main__ as cli
    from adaptive_rag.config import Settings, code_default_settings

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ADAPTIVE_RAG_TOP_K=9\nADAPTIVE_RAG_ADAPTIVE_FUSION=rrf\n")
    monkeypatch.setenv("ADAPTIVE_RAG_ADAPTIVE_HYBRID", "true")
    monkeypatch.setenv("ADAPTIVE_RAG_RETRIEVAL", "adaptive")
    leaky = Settings()  # the app's normal loading does pick these up
    assert (leaky.top_k, leaky.adaptive_fusion, leaky.adaptive_hybrid) == (9, "rrf", True)

    for settings in (code_default_settings(), cli._settings("dev", "embeddinggemma:300m", "C1")):
        assert settings.top_k == 5 and settings.retrieval == "baseline"
        assert settings.adaptive_hybrid is False and settings.adaptive_fusion == "weighted"
    assert cli._settings("dev", "m", "C7").chunking == "C7"  # explicit values still apply

    # Retrieval switches for a run come from its flags, which go into the run's metadata.
    args = argparse.Namespace(chunking="C1", retrieval="adaptive", table_prompt=False)
    run = cli._settings("dev", "m", "C1")
    run.retrieval, run.adaptive_hybrid, run.adaptive_fusion = "adaptive", True, "rrf"
    params = cli._metadata(
        args, run, type("E", (), {"version": lambda self: "v"})(), "dev", "x", "none"
    )
    assert params["adaptive_params"]["hybrid"] is True
    assert params["adaptive_params"]["fusion"] == "rrf"
