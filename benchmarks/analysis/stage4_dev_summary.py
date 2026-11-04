"""Stage 4 dev summary: choose B, score A/B/C on dev benchmark questions, and measure regret.

Inputs: the per-document optimizer results from optimize_dev.py, and the dev benchmark
questions (questions_dev.yaml answerable + questions_dev_tables.yaml).

- B: the single config with the best Recall@budget over all dev benchmark questions, chosen by
  the same selection rule as per-document optimization (ties go to the simplest).
- C: each dev document indexed with its own optimizer winner.
- A: C1 (fixed 512/50). All in one in-memory pool of the 4 dev documents, as in the retest.
- Regret, leave-one-out: for each document, a registry built from the other three; what the
  registry would do, and the Recall@budget lost against the document's own winner. Measured on
  the document's optimizer selection questions (saved scores) and on its dev benchmark
  questions. Four documents: anecdotal.

Every dev number here is optimistic for C7, whose detector was tuned on these documents.

Run from the repo root: python benchmarks/analysis/stage4_dev_summary.py <optimize results dir>
"""

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.evaluation.__main__ import DOCUMENTS
from adaptive_rag.evaluation.benchmark import load_manifest, load_questions
from adaptive_rag.evaluation.stats import mean_ci, paired_difference_ci
from adaptive_rag.loaders import LOADERS
from adaptive_rag.optimizer.candidates import BY_ID, CANDIDATES, build_chunks
from adaptive_rag.optimizer.embcache import CachedEmbeddings
from adaptive_rag.optimizer.optimize import Caps, _split
from adaptive_rag.optimizer.profile import Profile
from adaptive_rag.optimizer.registry import RATIO_FIELDS, _ratio, compare
from adaptive_rag.optimizer.scoring import (
    DocumentChunks,
    InMemoryIndex,
    question_spans,
    score_question,
)
from adaptive_rag.optimizer.selection import select
from adaptive_rag.providers import OllamaEmbeddings

MODEL = "embeddinggemma:300m"
HOST = "http://127.0.0.1:11434"
CACHE = Path("data/eval/embcache")
QUESTION_FILES = ("benchmarks/questions_dev.yaml", "benchmarks/questions_dev_tables.yaml")
EXTRACTION_FAILURES = {"tbl-nist-01", "tbl-nist-04"}


def numeric_distance(a: dict, b: dict) -> float:
    """Profile distance ignoring the structural flags, for the forced-nearest regret."""
    table = abs(a["table_share"] - b["table_share"]) / 0.05
    ratios = [_ratio(a[f], b[f]) for f in RATIO_FIELDS]
    return table + sum(math.log(r) / math.log(2.5) if math.isfinite(r) else 99.0 for r in ratios)


def reselect(run: dict) -> dict:
    """Re-apply the selection rule to a run's saved scores with the corrected split
    (confirmation at most a quarter). No LLM calls: the scores are the measured ones."""
    caps = Caps()
    order = [q["id"] for q in run["questions"]]
    selection, confirmation = _split(order, caps.confirmation_questions)
    scored = {c["id"]: c for c in run["candidates"] if c["status"] == "scored"}
    by_cand = {
        cid: {r["id"]: r["recall_at_budget"] for r in rows}
        for cid, rows in run["per_question"].items()
        if cid in scored
    }
    if len(selection) < caps.min_selection_questions or "C1" not in by_cand:
        return {
            "winner": "C1",
            "reason": f"only {len(selection)} selection questions",
            "rankings": [],
        }
    scores = {cid: [rows[i] for i in selection] for cid, rows in by_cand.items()}
    storage = {cid: scored[cid]["storage_tokens"] for cid in scores}
    winner, rankings = select(scores, storage)
    confirm = {
        cid: (sum(rows[i] for i in confirmation) / len(confirmation)) if confirmation else None
        for cid, rows in by_cand.items()
    }
    return {
        "winner": winner,
        "selection_questions": len(selection),
        "confirmation_questions": len(confirmation),
        "rankings": [vars(r) for r in rankings],
        "confirmation_recall": confirm,
        "reason": "tied with leader: "
        + ", ".join(r.candidate_id for r in rankings if r.tied_with_leader),
    }


def selection_recall(run: dict, selection_ids: list[str], candidate_id: str) -> float | None:
    """Mean Recall@budget of one candidate on a run's saved selection questions."""
    rows = {r["id"]: r for r in run["per_question"].get(candidate_id, [])}
    if not rows or not selection_ids:
        return None
    return sum(rows[i]["recall_at_budget"] for i in selection_ids) / len(selection_ids)


def main(results_dir: str) -> int:
    runs = {
        path.stem: json.loads(path.read_text())
        for path in sorted(Path(results_dir).glob("*.json"))
        if not path.stem.startswith("summary")
    }
    manifest = load_manifest(split="dev")
    docs = {m.name: LOADERS["pdf"].extract(DOCUMENTS / m.file) for m in manifest}
    by_doc = {run["document"]: run for run in runs.values()}
    missing = set(docs) - set(by_doc)
    if missing:
        raise SystemExit(f"optimizer results missing for {sorted(missing)}")
    corrected = {name: reselect(run) for name, run in by_doc.items()}
    for name, run in by_doc.items():
        run["original_winner"] = run["winner"]
        run["winner"] = corrected[name]["winner"]
        sel = set(_split([q["id"] for q in run["questions"]], 10)[0])
        for q in run["questions"]:
            q["split"] = "selection" if q["id"] in sel else "confirmation"

    questions = [q for f in QUESTION_FILES for q in load_questions(Path(f)) if q.answerable]
    spans = {q.id: question_spans(q, docs[q.document]) for q in questions}
    embedder = CachedEmbeddings(
        OllamaEmbeddings(MODEL, HOST, 32), CACHE / f"{MODEL.replace(':', '_')}.sqlite"
    )
    query = {q.id: embedder.embed_query(q.question) for q in questions}
    titles = {name: name.rsplit(".", 1)[0] for name in docs}

    def chunks_for(cid: str, name: str):
        return build_chunks(BY_ID[cid], docs[name], embedder, titles[name])

    def score(assignment: dict[str, str]) -> dict[str, dict]:
        parts = [DocumentChunks(n, docs[n], chunks_for(assignment[n], n), titles[n]) for n in docs]
        index = InMemoryIndex(parts, embedder)
        return {
            q.id: vars(score_question(index, query[q.id], q.id, spans[q.id])) for q in questions
        }

    # Global configs: every candidate applied to every document.
    global_scores = {c.id: score(dict.fromkeys(docs, c.id)) for c in CANDIDATES}
    ids = [q.id for q in questions]
    rab = {cid: [s[i]["recall_at_budget"] for i in ids] for cid, s in global_scores.items()}
    storage = {}
    for c in CANDIDATES:
        storage[c.id] = sum(ch.token_count for n in docs for ch in chunks_for(c.id, n))
    b_winner, b_rankings = select(rab, storage)

    c_assignment = {name: by_doc[name]["winner"] for name in docs}
    c_scores = score(c_assignment)

    def subset(group: str) -> list[str]:
        if group == "all":
            return ids
        if group == "table_clean":
            return [
                q.id for q in questions if q.type == "table" and q.id not in EXTRACTION_FAILURES
            ]
        if group == "table_extraction_failures":
            return [i for i in ids if i in EXTRACTION_FAILURES]
        return [q.id for q in questions if q.type != "table"]

    systems = {
        "A (C1)": global_scores["C1"],
        f"B ({b_winner})": global_scores[b_winner],
        "C": c_scores,
    }
    comparison = {}
    for group in ("all", "table_clean", "non_table", "table_extraction_failures"):
        sel = subset(group)
        row = {"n": len(sel)}
        for label, s in systems.items():
            row[label] = {
                m: mean_ci([s[i][m] for i in sel])
                for m in ("recall_at_budget", "hit_at_5", "reciprocal_rank")
            }
        a = [systems["A (C1)"][i]["recall_at_budget"] for i in sel]
        b = [systems[f"B ({b_winner})"][i]["recall_at_budget"] for i in sel]
        c = [c_scores[i]["recall_at_budget"] for i in sel]
        row["C_minus_B"] = paired_difference_ci(c, b)
        row["C_minus_A"] = paired_difference_ci(c, a)
        row["B_minus_A"] = paired_difference_ci(b, a)
        comparison[group] = row

    # Regret, leave-one-out.
    regret = {}
    for name in docs:
        own = by_doc[name]
        others = [by_doc[n] for n in docs if n != name]
        profile = Profile(**own["profile"])
        matches = []
        for other in others:
            kind, distance = compare(profile, other["profile"])
            matches.append(
                (kind, distance, numeric_distance(own["profile"], other["profile"]), other)
            )
        usable = [m for m in matches if m[0] != "different"]
        if usable:
            kind, distance, _, entry = min(usable, key=lambda m: m[1])
            action = "reuse" if kind == "strong" else "retest"
        else:
            kind, distance, entry, action = "different", None, None, "optimize"
        nearest = min(matches, key=lambda m: m[2])[3]

        sel_ids = [q["id"] for q in own["questions"] if q["split"] == "selection"]
        bench_ids = [q.id for q in questions if q.document == name]
        part = {"name": name, "doc": docs[name], "title": titles[name]}

        def sel_recall(cid, own=own, sel_ids=sel_ids):
            return selection_recall(own, sel_ids, cid)

        def bench_recall(cid, part=part, bench_ids=bench_ids):
            chunks = chunks_for(cid, part["name"])
            index = InMemoryIndex(
                [DocumentChunks(part["name"], part["doc"], chunks, part["title"])], embedder
            )
            scores = [score_question(index, query[i], i, spans[i]) for i in bench_ids]
            return sum(x.recall_at_budget for x in scores) / len(scores)

        winner = own["winner"]
        chosen = entry["winner"] if entry else winner
        forced = nearest["winner"]
        regret[name] = {
            "own_winner": winner,
            "registry_action": action,
            "match": kind,
            "match_source": entry["document"] if entry else None,
            "config_used": chosen if action != "optimize" else winner,
            "forced_nearest_source": nearest["document"],
            "forced_nearest_config": forced,
            "selection_questions": len(sel_ids),
            "regret_selection_qs": None
            if action == "optimize" or sel_recall(chosen) is None
            else round(sel_recall(winner) - sel_recall(chosen), 4),
            "forced_regret_selection_qs": None
            if sel_recall(forced) is None
            else round(sel_recall(winner) - sel_recall(forced), 4),
            "benchmark_questions": len(bench_ids),
            "forced_regret_benchmark_qs": round(bench_recall(winner) - bench_recall(forced), 4),
        }

    summary = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "optimizer_results": results_dir,
        "caveat": (
            "C7's detector was tuned on these dev documents; dev scores using C7 are optimistic."
        ),
        "per_document": {
            name: {
                "winner": by_doc[name]["winner"],
                "original_winner": by_doc[name]["original_winner"],
                "original_reason": by_doc[name]["winner_reason"],
                "corrected_selection": corrected[name],
                "ingest_timings_s": by_doc[name]["ingest_timings_s"],
                "timings_s": by_doc[name]["timings_s"],
                "questions": [
                    by_doc[name]["questions_selection"],
                    by_doc[name]["questions_confirmation"],
                ],
                "question_types": by_doc[name]["question_types"],
                "rejected": by_doc[name]["rejected"],
                "llm_calls": by_doc[name]["llm_calls"],
                "stopped_early": by_doc[name]["stopped_early"],
                "sample_tokens": by_doc[name]["sample_tokens"],
                "candidates": by_doc[name]["candidates"],
                "profile": by_doc[name]["profile"],
            }
            for name in docs
        },
        "B": {
            "winner": b_winner,
            "rankings": [vars(r) for r in b_rankings],
            "storage_tokens": storage,
        },
        "comparison": comparison,
        "regret": regret,
        "per_question": {"global": global_scores, "C": c_scores},
    }
    out = Path(results_dir) / "summary.json"
    out.write_text(json.dumps(summary, indent=2, default=list))
    print(f"B = {b_winner}; C = {c_assignment}")
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
