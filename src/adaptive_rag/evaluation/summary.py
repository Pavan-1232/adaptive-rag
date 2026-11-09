"""A read-only summary of the held-out results, for the UI. Every number is read from the committed
Stage 4 and Stage 5 report files at request time; nothing is copied or estimated here."""

import json
from pathlib import Path

STAGE4_REPORT = "stage4_test_report_20261104T093653.json"
STAGE5_REPORT = "stage5_test_report_20261105T152950.json"


def verdict(difference: list[float]) -> str:
    """Plain words for a paired difference [mean, CI low, CI high] (decision 69)."""
    mean, low, high = difference
    if low > 0:
        return "better than baseline"
    if high < 0:
        return "worse than baseline"
    if mean == low == high == 0:
        return "identical to baseline"
    return "inconclusive: not shown to be better than baseline"


def _comparison(name: str, metric: str, n: int, difference: list[float], note: str) -> dict:
    return {
        "name": name,
        "metric": metric,
        "n": n,
        "difference": difference[0],
        "ci_low": difference[1],
        "ci_high": difference[2],
        "verdict": verdict(difference),
        "note": note,
    }


def evaluation_summary(results_dir: Path) -> dict:
    stage4 = json.loads((results_dir / STAGE4_REPORT).read_text())
    stage5 = json.loads((results_dir / STAGE5_REPORT).read_text())
    baseline = stage5["summaries"]["A"]
    c7 = stage4["primary_C7_vs_A"]
    c = stage4["secondary_C"]["all_answerable"]
    s = stage5["primary"]
    recall = "Recall@budget (2,560 tokens)"
    return {
        "dataset": (
            "Held-out test set: 5 public documents, 30 questions (24 answerable), run once. "
            "Measured without MCQ answer-key linking and the MCQ option check (both added "
            "2026-11-09)."
        ),
        "baseline": {
            "name": "A: fixed 512/50 chunks, top-5 retrieval",
            "answerable": baseline["answerable"],
            "unanswerable": baseline["unanswerable"],
            "recall_at_budget": baseline["recall_at_budget"],
            "hit_at_5": baseline["hit_at_5"],
            "reciprocal_rank": baseline["reciprocal_rank"],
            "unanswerable_refused": baseline["unanswerable_refused"],
            "generation_p50_s": baseline["generation_p50_s"],
        },
        "comparisons": [
            _comparison(
                "C7 table-aware chunks vs A, table questions",
                recall,
                c7["table"]["n"],
                c7["table"]["recall_at_budget"]["difference"],
                "The gain is one question; C7's detector was tuned on dev documents.",
            ),
            _comparison(
                "C7 table-aware chunks vs A, all questions",
                recall,
                c7["all_answerable"]["n"],
                c7["all_answerable"]["recall_at_budget"]["difference"],
                "",
            ),
            _comparison(
                "C chunking optimizer vs A",
                recall,
                c7["all_answerable"]["n"],
                c["C_minus_A"]["difference"],
                "The optimizer chose the baseline's chunking for every document.",
            ),
            _comparison(
                "S adaptive retrieval vs A",
                "Recall over the evidence sent (2,560 tokens)",
                s["n"],
                s["S_minus_A"],
                "S sends fewer tokens on average; its losses come from the gap cutoff and "
                "question splitting.",
            ),
        ],
        "sources": [f"benchmarks/results/{STAGE4_REPORT}", f"benchmarks/results/{STAGE5_REPORT}"],
    }
