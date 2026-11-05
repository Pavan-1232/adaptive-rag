"""Summaries and the Markdown report. Every number comes from recorded results."""

from statistics import quantiles

from .stats import mean_ci


def _values(results: list[dict], key: str) -> list[float]:
    return [r[key] for r in results if r.get(key) is not None]


def _percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[percent - 1]


def summarize(results: list[dict]) -> dict:
    answerable = [r for r in results if r["answerable"]]
    unanswerable = [r for r in results if not r["answerable"]]
    summary: dict = {
        "questions": len(results),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
    }
    for key in ("recall_at_budget", "recall_at_5", "hit_at_5", "reciprocal_rank"):
        values = _values(answerable, key)
        summary[key] = mean_ci(values) if values else None
    # Part coverage is reported for questions with two or more required facts only.
    multi = [r for r in answerable if (r.get("parts") or 0) >= 2]
    summary["multi_part_questions"] = len(multi)
    for key in ("part_coverage", "all_parts_covered"):
        values = _values(multi, key)
        summary[key] = mean_ci(values) if values else None

    answered = [r for r in answerable if r.get("status") == "answered"]
    summary["answered"] = len(answered)
    summary["answerable_status"] = {
        status: sum(r.get("status") == status for r in answerable)
        for status in ("answered", "partial", "insufficient", None)
    }
    off_evidence = [r for r in answered if not r.get("citation_on_evidence")]
    summary["wrong_focus_by_citation"] = len(off_evidence)
    summary["wrong_focus_by_citation_rate"] = (
        len(off_evidence) / len(answered) if answered else None
    )
    judged = [r for r in answered if r.get("addresses_question") is not None]
    off_topic = [r for r in judged if not r["addresses_question"]]
    summary["wrong_focus_by_judge"] = len(off_topic)
    summary["judged"] = len(judged)
    summary["wrong_focus_by_judge_rate"] = len(off_topic) / len(judged) if judged else None
    compared = [r for r in answered if r.get("reference_verdict") is not None]
    summary["reference_compared"] = len(compared)
    for verdict in ("conflicts", "different_point"):
        summary[f"reference_{verdict}"] = sum(r["reference_verdict"] == verdict for r in compared)
    summary["wrong_focus_either"] = len(
        {r["id"] for r in off_evidence} | {r["id"] for r in off_topic}
    )

    faithfulness = _values(results, "faithfulness")
    summary["faithfulness"] = mean_ci(faithfulness) if faithfulness else None
    precision = _values(answerable, "citation_precision")
    summary["citation_precision"] = mean_ci(precision) if precision else None
    summary["false_answers"] = sum(r.get("status") in ("answered", "partial") for r in unanswerable)
    summary["unanswerable_refused"] = sum(r.get("status") == "insufficient" for r in unanswerable)
    summary["errors"] = sum(bool(r.get("error")) for r in results)

    latency = [r["timings_ms"].get("generation") for r in results if r.get("timings_ms")]
    latency = [value / 1000 for value in latency if value is not None]
    summary["generation_p50_s"] = _percentile(latency, 50)
    summary["generation_p95_s"] = _percentile(latency, 95)
    tokens = _values(results, "input_tokens")
    summary["avg_input_tokens"] = sum(tokens) / len(tokens) if tokens else None
    outputs = _values(results, "output_tokens")
    summary["avg_output_tokens"] = sum(outputs) / len(outputs) if outputs else None
    return summary


def _ci(value) -> str:
    if value is None:
        return "not measured"
    mean, low, high = value
    return f"{mean:.3f} (95% CI {low:.3f}–{high:.3f})"


def _number(value, pattern: str = "{:.1f}") -> str:
    return "not measured" if value is None else pattern.format(value)


def render_markdown(metadata: dict, summary: dict) -> str:
    status = summary["answerable_status"]
    lines = [
        f"# Evaluation report: {metadata.get('system', '?')} on {metadata.get('set', '?')}",
        "",
        f"- Generated: {metadata.get('created_at', '?')}",
        f"- Commit: {metadata.get('commit', '?')}",
        f"- Embedding model: {metadata.get('embedding_model', '?')} "
        f"({metadata.get('embedding_version', '?')[:12]})",
        f"- LLM: {metadata.get('llm_model', '?')}; judge: {metadata.get('judge_model', 'none')}",
        f"- Machine: {metadata.get('machine', '?')}",
        f"- Questions: {summary['questions']} ({summary['answerable']} answerable, "
        f"{summary['unanswerable']} unanswerable)",
        f"- Question source: {metadata.get('question_source', '?')}",
        "- Recall@budget is comparable only between runs with the same token budget.",
        "",
        "## Retrieval (answerable questions)",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Recall@budget ({metadata.get('recall_budget_tokens', '?')} tokens), primary | "
        f"{_ci(summary['recall_at_budget'])} |",
        f"| Recall@5 | {_ci(summary['recall_at_5'])} |",
        f"| Hit rate@5 | {_ci(summary['hit_at_5'])} |",
        f"| MRR | {_ci(summary['reciprocal_rank'])} |",
        f"| Part coverage ({summary.get('multi_part_questions', 0)} questions with 2+ parts) | "
        f"{_ci(summary.get('part_coverage'))} |",
        f"| All parts covered | {_ci(summary.get('all_parts_covered'))} |",
        "",
        "## Answers",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Answerable marked answered / partial / insufficient / no result | "
        f"{status['answered']} / {status['partial']} / {status['insufficient']} / {status[None]} |",
        f"| Wrong focus: `answered`, no citation on gold evidence | "
        f"{summary['wrong_focus_by_citation']} of {summary['answered']} |",
        f"| Wrong focus: `answered`, judge says it misses the question | "
        f"{summary['wrong_focus_by_judge']} of {summary['judged']} |",
        f"| Wrong focus: either signal | {summary['wrong_focus_either']} of "
        f"{summary['answered']} |",
        f"| `answered`, gold comparison says conflicts / different point | "
        f"{summary['reference_conflicts']} / {summary['reference_different_point']} of "
        f"{summary['reference_compared']} |",
        f"| Citation precision against gold evidence | {_ci(summary['citation_precision'])} |",
        f"| Faithfulness (LLM judge, not ground truth) | {_ci(summary['faithfulness'])} |",
        f"| Unanswerable refused by the LLM, gate off | {summary['unanswerable_refused']} of "
        f"{summary['unanswerable']} |",
        f"| False answers on unanswerable, gate off | {summary['false_answers']} of "
        f"{summary['unanswerable']} |",
        f"| Generation time p50 / p95 | {_number(summary['generation_p50_s'])} s / "
        f"{_number(summary['generation_p95_s'])} s |",
        f"| Average input / output tokens | {_number(summary['avg_input_tokens'], '{:.0f}')} / "
        f"{_number(summary['avg_output_tokens'], '{:.0f}')} |",
        f"| Generation errors | {summary['errors']} |",
        "",
    ]
    if metadata.get("notes"):
        lines += ["## Notes", "", metadata["notes"], ""]
    return "\n".join(lines)
