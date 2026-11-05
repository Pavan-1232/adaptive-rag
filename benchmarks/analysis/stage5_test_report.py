"""Stage 5 held-out report, as pre-registered (PROGRESS.md decision 56). Run after S finishes.

Primary: S minus A on recall over sent evidence, all 24 answerable, paired CI.
A's value is its saved Stage 4 recall_at_budget; a retrieval-only replay of A on the same
index checks it and supplies A's part coverage. Nothing here changes any system.

Run from the repo root: python data/eval/stage5_test_report.py <A results> <S results>
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.evaluation.__main__ import DOCUMENTS, _providers, _settings
from adaptive_rag.evaluation.benchmark import load_manifest, load_questions
from adaptive_rag.evaluation.report import summarize
from adaptive_rag.evaluation.runner import (
    build_index,
    evaluate_retrieval,
    evidence_spans,
    is_complete,
)
from adaptive_rag.evaluation.stats import is_tie, mean_ci, paired_difference_ci

QUESTIONS = Path("benchmarks/questions_test.yaml")
SEEN = ("fed-02", "fed-04", "bp-03")


def verdict(ci) -> str:
    return (
        "inconclusive (CI includes 0)" if is_tie(ci) else ("S better" if ci[1] > 0 else "S worse")
    )


def replay_a(questions) -> dict[str, dict]:
    settings = _settings("test", "embeddinggemma:300m", "C1")  # retrieval = baseline (A)
    assert settings.retrieval == "baseline"
    embedder, llm = _providers(settings)
    ctx, kb, indexed = build_index(
        settings, embedder, llm, load_manifest(split="test"), DOCUMENTS, "benchmark-test"
    )
    out = {}
    for q in questions:
        result, _ = evaluate_retrieval(ctx, kb, q, evidence_spans(q, indexed))
        out[q.id] = {
            "recall_at_budget": result.recall_at_budget,
            "recall_sent": result.recall_sent,
            "part_coverage_sent": result.part_coverage_sent,
        }
    return out


def main(a_path: str, s_path: str) -> int:
    runs = {label: json.loads(Path(p).read_text()) for label, p in (("A", a_path), ("S", s_path))}
    for label, run in runs.items():
        if not is_complete(run):
            raise SystemExit(f"{label} is incomplete")
    a = {r["id"]: r for r in runs["A"]["results"]}
    s = {r["id"]: r for r in runs["S"]["results"]}
    questions = load_questions(QUESTIONS)
    answerable = [q for q in questions if q.answerable]
    ids = [q.id for q in answerable]
    by_type = {t: [q.id for q in answerable if q.type == t] for t in ("table", "multi_part")}

    replay = replay_a(answerable)
    mismatch = [
        i
        for i in ids
        if abs(replay[i]["recall_at_budget"] - a[i]["recall_at_budget"]) > 1e-9
        or abs(replay[i]["recall_sent"] - a[i]["recall_at_budget"]) > 1e-9
    ]

    a_sent = [a[i]["recall_at_budget"] for i in ids]
    s_sent = [s[i]["recall_sent"] for i in ids]
    primary = {
        "n": len(ids),
        "A_mean": mean_ci(a_sent),
        "S_mean": mean_ci(s_sent),
        "S_minus_A": paired_difference_ci(s_sent, a_sent),
    }
    primary["verdict"] = verdict(primary["S_minus_A"])
    if mismatch:
        a_replay = [replay[i]["recall_sent"] for i in ids]
        primary["S_minus_A_replay_sent"] = paired_difference_ci(s_sent, a_replay)

    mp = by_type["multi_part"]
    parts = {
        "n": len(mp),
        "S_part_coverage_sent": [s[i]["part_coverage_sent"] for i in mp],
        "S_all_parts": sum(s[i]["part_coverage_sent"] == 1.0 for i in mp),
        "A_part_coverage_sent": None if mismatch else [replay[i]["part_coverage_sent"] for i in mp],
        "A_all_parts": None
        if mismatch
        else sum(replay[i]["part_coverage_sent"] == 1.0 for i in mp),
        "ids": mp,
    }
    tables = {
        "n": len(by_type["table"]),
        "A_agrees": sum(a[i]["reference_verdict"] == "agrees" for i in by_type["table"]),
        "S_agrees": sum(s[i]["reference_verdict"] == "agrees" for i in by_type["table"]),
        "rows": {
            i: [a[i]["reference_verdict"], s[i]["reference_verdict"]] for i in by_type["table"]
        },
    }
    summ = {label: summarize(run["results"]) for label, run in runs.items()}
    unanswerable = [q.id for q in questions if not q.answerable]
    guard = {
        "S_refused": sum(s[i]["status"] == "insufficient" for i in unanswerable),
        "of": len(unanswerable),
        "S_false_refusals": [i for i in ids if s[i]["status"] == "insufficient"],
        "A_false_refusals": [i for i in ids if a[i]["status"] == "insufficient"],
        "p50_s": {label: summ[label]["generation_p50_s"] for label in runs},
    }

    def view(label, r, i):
        return {
            "recall_sent": r[i]["recall_sent"] if label == "S" else r[i]["recall_at_budget"],
            "status": r[i]["status"],
            "reference_verdict": r[i]["reference_verdict"],
            "answer": (r[i]["answer"] or "")[:300],
        }

    seen = {i: {"A": view("A", a, i), "S": view("S", s, i)} for i in SEEN}
    changed = [
        [i, a[i]["recall_at_budget"], s[i]["recall_sent"]]
        for i in ids
        if abs(a[i]["recall_at_budget"] - s[i]["recall_sent"]) > 1e-9
    ]
    report = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "pre_registered": "PROGRESS.md decision 56",
        "files": {"A": a_path, "S": s_path},
        "commits": {label: run["metadata"]["commit"] for label, run in runs.items()},
        "replay_mismatch": mismatch,
        "primary": primary,
        "changed_questions": changed,
        "secondary_parts": parts,
        "secondary_tables": tables,
        "guardrails": guard,
        "tokens_sent_S": mean_ci([s[i]["tokens_sent"] for i in ids]),
        "summaries": summ,
        "seen": seen,
        "replay_A": replay,
    }
    out = Path("benchmarks/results") / f"stage5_test_report_{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, default=list))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:3]))
