"""Stage 4 held-out report, as pre-registered (PROGRESS.md decision 42).

Reads the three completed test result files (A = C1, C7, C = adaptive) and the index folders
they built. Order of the report: the primary comparison (C7 vs A, table questions then all
answerable), then C, then the post-hoc Fed breakdown. Nothing here changes any system.

Run from the repo root:
    python benchmarks/analysis/stage4_test_report.py <A results> <C7 results> <C results>
"""

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.evaluation.benchmark import load_questions
from adaptive_rag.evaluation.report import summarize
from adaptive_rag.evaluation.runner import is_complete
from adaptive_rag.evaluation.spans import locate_quote, page_range
from adaptive_rag.evaluation.stats import is_tie, mean_ci, paired_difference_ci

QUESTIONS = Path("benchmarks/questions_test.yaml")
FOLDERS = {
    "A": Path("data/eval/test_embeddinggemma_300m_C1"),
    "C7": Path("data/eval/test_embeddinggemma_300m_C7"),
    "C": Path("data/eval/test_embeddinggemma_300m_adaptive"),
}
METRICS = ("recall_at_budget", "hit_at_5", "reciprocal_rank")
FED = "fed_mpr.pdf"


def verdict(ci) -> str:
    if is_tie(ci):
        return "inconclusive (CI includes 0)"
    return "better" if ci[1] > 0 else "worse"


def paired(first: dict, second: dict, ids: list[str], metric: str) -> dict:
    ci = paired_difference_ci([first[i][metric] for i in ids], [second[i][metric] for i in ids])
    return {"difference": ci, "verdict": verdict(ci)}


def gold_in_one_chunk(folder: Path, question) -> bool | None:
    """Whether one stored chunk contains a whole gold span (any listed location)."""
    conn = sqlite3.connect(folder / "adaptive_rag.sqlite")
    conn.row_factory = sqlite3.Row
    doc = conn.execute(
        "SELECT id, canonical_text, units FROM documents WHERE filename = ? AND status = 'ready'",
        (question.document,),
    ).fetchone()
    if doc is None:
        return None
    units = json.loads(doc["units"])
    chunks = conn.execute(
        "SELECT start_char, end_char FROM chunks WHERE document_id = ?", (doc["id"],)
    ).fetchall()
    for item in question.evidence:
        for option in (item, *item.alternatives):
            span = locate_quote(doc["canonical_text"], option.quote, page_range(units, option.page))
            if span and any(
                c["start_char"] <= span[0] and span[1] <= c["end_char"] for c in chunks
            ):
                return True
    return False


def choices(folder: Path) -> list[dict]:
    conn = sqlite3.connect(folder / "adaptive_rag.sqlite")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT d.filename, r.action, r.candidate_id, r.seconds, r.detail FROM optimization_runs r"
        " JOIN documents d ON d.id = r.document_id ORDER BY r.id"
    ).fetchall()
    out = []
    for row in rows:
        detail = json.loads(row["detail"])
        opt = detail.get("optimization") or {}
        out.append(
            {
                "document": row["filename"],
                "action": row["action"],
                "candidate": row["candidate_id"],
                "seconds": row["seconds"],
                "match": (detail.get("match") or {}).get("reason"),
                "reason": opt.get("winner_reason"),
                "questions": [opt.get("questions_selection"), opt.get("questions_confirmation")],
                "question_types": opt.get("question_types"),
                "stopped_early": opt.get("stopped_early"),
                "timings_s": opt.get("timings_s"),
            }
        )
    return out


def main(a_path: str, c7_path: str, c_path: str) -> int:
    runs = {}
    for label, path in (("A", a_path), ("C7", c7_path), ("C", c_path)):
        payload = json.loads(Path(path).read_text())
        if not is_complete(payload):
            raise SystemExit(f"{path} is incomplete; resume it first")
        runs[label] = payload
    commits = {label: run["metadata"]["commit"] for label, run in runs.items()}
    rows = {label: {r["id"]: r for r in run["results"]} for label, run in runs.items()}
    questions = load_questions(QUESTIONS)
    answerable = [q.id for q in questions if q.answerable]
    table = [q.id for q in questions if q.answerable and q.type == "table"]
    by_id = {q.id: q for q in questions}

    primary = {
        group: {
            "n": len(ids),
            **{m: paired(rows["C7"], rows["A"], ids, m) for m in METRICS},
            "means": {
                label: {m: mean_ci([rows[label][i][m] for i in ids]) for m in METRICS}
                for label in ("A", "C7")
            },
        }
        for group, ids in (("table", table), ("all_answerable", answerable))
    }
    secondary = {
        group: {
            "C_minus_A": paired(rows["C"], rows["A"], ids, "recall_at_budget"),
            "C_minus_C7": paired(rows["C"], rows["C7"], ids, "recall_at_budget"),
            "C_mean": mean_ci([rows["C"][i]["recall_at_budget"] for i in ids]),
        }
        for group, ids in (("table", table), ("all_answerable", answerable))
    }
    summaries = {label: summarize(run["results"]) for label, run in runs.items()}

    def answer_view(label: str, qid: str) -> dict:
        r = rows[label][qid]
        rr = r.get("reciprocal_rank")
        return {
            "status": r.get("status"),
            "recall_at_budget": r.get("recall_at_budget"),
            "gold_rank": round(1 / rr) if rr else None,
            "reference_verdict": r.get("reference_verdict"),
            "citation_on_evidence": r.get("citation_on_evidence"),
            "answer": r.get("answer"),
        }

    tracked = {
        qid: {label: answer_view(label, qid) for label in runs} for qid in ("bp-03", "fed-02")
    }
    fed = []
    for q in questions:
        if q.document != FED:
            continue
        entry = {"id": q.id, "type": q.type, "answerable": q.answerable}
        for label in runs:
            view = answer_view(label, q.id)
            view.pop("answer")
            if q.answerable:
                view["gold_in_one_chunk"] = gold_in_one_chunk(FOLDERS[label], by_id[q.id])
            entry[label] = view
        fed.append(entry)

    report = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": {"A": a_path, "C7": c7_path, "C": c_path},
        "commits": commits,
        "same_commit": len(set(commits.values())) == 1,
        "pre_registered": "PROGRESS.md decision 42",
        "caveat": "C7's detector was tuned on dev; its dev scores are optimistic. This held-out "
        "run is the only evidence for C7.",
        "primary_C7_vs_A": primary,
        "secondary_C": secondary,
        "summaries": summaries,
        "C_choices": choices(FOLDERS["C"]),
        "tracked_wrong_answers": tracked,
        "fed_post_hoc": fed,
    }
    out = Path("benchmarks/results") / f"stage4_test_report_{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, default=list))
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
