"""Stage 5 retrieval-only sweep on dev. No LLM calls; query embeddings are cached.

Usage: python benchmarks/analysis/stage5_sweep.py

Scores each AdaptiveParams config on the 56 answerable dev questions (dev, dev tables, dev
multi-part) by recall over the evidence actually sent, part coverage and tokens sent, and
compares with A (top-5, 2560 tokens). Writes benchmarks/results/stage5_sweep_<stamp>.json.

Selection rule, fixed before the first run (PROGRESS.md decision 49): highest mean recall
sent; a feature stays on only if switching it off lowers recall sent or part coverage.
The script applies that rule itself (ablate()) at each budget.

2026-11-05 rerun adds: gap cutoff, span merging, per-document cap, neighbor reserve, and
hybrid FTS5 keyword search. Search results are cached per text, so configs differ only in
selection.
"""

import itertools
import json
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from adaptive_rag.evaluation.__main__ import DOCUMENTS, RESULTS, _providers, _settings
from adaptive_rag.evaluation.benchmark import load_manifest, load_questions
from adaptive_rag.evaluation.metrics import evidence_recall, part_coverage
from adaptive_rag.evaluation.runner import _ranked, build_index, evidence_spans
from adaptive_rag.evaluation.stats import mean_ci, paired_difference_ci
from adaptive_rag.retrieval import (
    AdaptiveParams,
    adaptive,
    fit_to_budget,
    retrieve_adaptive,
    retrieve_baseline,
)

FILES = ["questions_dev.yaml", "questions_dev_tables.yaml", "questions_dev_multipart.yaml"]
MODEL = "embeddinggemma:300m"


def load_dev():
    settings = _settings("dev", MODEL, "C1")
    embedder, llm = _providers(settings)
    ctx, kb, indexed = build_index(
        settings, embedder, llm, load_manifest(split="dev"), DOCUMENTS, "benchmark-dev"
    )
    cached = lru_cache(maxsize=None)(embedder.embed_query)
    embedder.embed_query = cached  # same vectors, computed once per text
    _cache_search()
    questions = []
    for name in FILES:
        for question in load_questions(Path("benchmarks") / name):
            if question.answerable:
                questions.append((name, question, evidence_spans(question, indexed)))
    return ctx, kb, questions


def _cache_search() -> None:
    """Pools depend only on the text and the search switches; neighbors only on position."""
    pool, neighbor = adaptive._pool, adaptive.load_neighbor
    pools: dict = {}
    neighbors: dict = {}

    def cached_pool(ctx, kb, text, params, document_ids):
        key = (text, params.pool_size, params.hybrid, params.keyword_pool)
        if key not in pools:
            pools[key] = pool(ctx, kb, text, params, document_ids)
        return pools[key]

    def cached_neighbor(ctx, document_id, index, score):
        key = (document_id, index)
        if key not in neighbors:
            neighbors[key] = neighbor(ctx, document_id, index, 0.0)
        found = neighbors[key]
        return None if found is None else replace(found, score=score)

    adaptive._pool = cached_pool
    adaptive.load_neighbor = cached_neighbor


def score(rows: list[dict]) -> dict:
    multi = [r for r in rows if r["parts"] >= 2]
    tables = [r for r in rows if r["type"] == "table"]
    return {
        "recall_sent": mean_ci([r["recall"] for r in rows]),
        "recall_sent_tables": mean_ci([r["recall"] for r in tables]),
        "recall_sent_multi": mean_ci([r["recall"] for r in multi]),
        "part_coverage_multi": mean_ci([r["coverage"] for r in multi]),
        "all_parts_multi": sum(r["coverage"] == 1.0 for r in multi),
        "multi_n": len(multi),
        "tokens_mean": sum(r["tokens"] for r in rows) / len(rows),
        "tokens_max": max(r["tokens"] for r in rows),
        "chunks_mean": sum(r["chunks"] for r in rows) / len(rows),
        "merged_tokens_saved": sum(r["merged_tokens_saved"] for r in rows),
        "duplicate_tokens": sum(r["duplicate_tokens"] for r in rows),
    }


def run_baseline(ctx, kb, questions) -> list[dict]:
    rows = []
    for name, question, spans in questions:
        used = fit_to_budget(retrieve_baseline(ctx, kb, question.question, 5), 4000)
        rows.append(_row(name, question, spans, used))
    return rows


def run_config(ctx, kb, questions, params: AdaptiveParams) -> list[dict]:
    rows = []
    for name, question, spans in questions:
        result = retrieve_adaptive(ctx, kb, question.question, params)
        row = _row(name, question, spans, result.chunks, result.duplicate_tokens)
        row.update(
            kind=result.plan.kind,
            stop=result.stop_reason,
            merged_tokens_saved=result.merged_tokens_saved,
            uncovered=len(result.uncovered_parts),
        )
        rows.append(row)
    return rows


def _row(name, question, spans, used, duplicate_tokens=0) -> dict:
    sent = _ranked(used)
    return {
        "part_hits": [part_coverage(sent, [span], 10**9) == 1.0 for span in spans],
        "merged_tokens_saved": 0,
        "file": name,
        "id": question.id,
        "type": question.type,
        "parts": len(spans),
        "recall": evidence_recall(sent, spans),
        "coverage": part_coverage(sent, spans, 10**9),
        "tokens": sum(c.evidence_tokens for c in used),
        "chunks": len(used),
        "duplicate_tokens": duplicate_tokens,
    }


AXES = {
    "budget": (2560, 4000),
    "split_parts": (False, True),
    "delta": (None, 0.05, 0.10, 0.15),
    "gap_cutoff": (False, True),
    "dedupe": (False, True),
    "merge_spans": (False, True),
    "doc_cap": (None, 3),
    "neighbors": ("off", "on, no reserve", "on, 30% reserve"),
    "keyword_weight": (None, 0.05, 0.10, 0.20),  # None = hybrid off
}
OFF = {
    "split_parts": False,
    "delta": None,
    "gap_cutoff": False,
    "dedupe": False,
    "merge_spans": False,
    "doc_cap": None,
    "neighbors": "off",
    "keyword_weight": None,
}


def to_params(point: dict) -> AdaptiveParams:
    weight = point["keyword_weight"]
    return AdaptiveParams(
        budget=point["budget"],
        split_parts=point["split_parts"],
        delta=point["delta"],
        gap_cutoff=point["gap_cutoff"],
        dedupe=point["dedupe"],
        merge_spans=point["merge_spans"],
        doc_cap=point["doc_cap"],
        neighbors=point["neighbors"] != "off",
        neighbor_reserve=0.3 if point["neighbors"] == "on, 30% reserve" else 0.0,
        hybrid=weight is not None,
        keyword_weight=weight or 0.0,
    )


def grid() -> list[dict]:
    return [dict(zip(AXES, values, strict=True)) for values in itertools.product(*AXES.values())]


def _key(point: dict) -> tuple:
    return tuple(point[name] for name in AXES)


def _better(a: dict, b: dict) -> bool:
    """a beats b: higher recall sent, then part coverage; equal means not better."""
    sa, sb = a["summary"], b["summary"]
    return (sa["recall_sent"][0], sa["part_coverage_multi"][0]) > (
        sb["recall_sent"][0],
        sb["part_coverage_multi"][0],
    )


def ablate(best: dict, by_key: dict) -> tuple[dict, list[dict]]:
    """Decision 49: switch each feature off in turn; keep it off unless that lowers recall
    sent or part coverage. Repeat until nothing changes."""
    current, log = best, []
    changed = True
    while changed:
        changed = False
        for name, off in OFF.items():
            if current["point"][name] == off:
                continue
            candidate = by_key[_key({**current["point"], name: off})]
            cs, os_ = current["summary"], candidate["summary"]
            lowers = (
                os_["recall_sent"][0] < cs["recall_sent"][0] - 1e-9
                or os_["part_coverage_multi"][0] < cs["part_coverage_multi"][0] - 1e-9
            )
            log.append(
                {
                    "feature": name,
                    "on": current["point"][name],
                    "recall_on": cs["recall_sent"][0],
                    "recall_off": os_["recall_sent"][0],
                    "parts_on": cs["part_coverage_multi"][0],
                    "parts_off": os_["part_coverage_multi"][0],
                    "kept": lowers,
                }
            )
            if not lowers:
                current, changed = candidate, True
    return current, log


def _line(o: dict) -> str:
    s = o["summary"]
    return (
        f"{o['point']} | recall {s['recall_sent'][0]:.3f} tbl {s['recall_sent_tables'][0]:.3f}"
        f" parts {s['part_coverage_multi'][0]:.3f} all {s['all_parts_multi']}/{s['multi_n']}"
        f" tok {s['tokens_mean']:.0f} | vs A {o['vs_A'][0]:+.3f}"
        f" ({o['vs_A'][1]:+.3f},{o['vs_A'][2]:+.3f})"
    )


def main() -> int:
    ctx, kb, questions = load_dev()
    baseline_rows = run_baseline(ctx, kb, questions)
    baseline = score(baseline_rows)
    print(
        f"A: recall {baseline['recall_sent'][0]:.3f} parts {baseline['part_coverage_multi'][0]:.3f}"
        f" all-parts {baseline['all_parts_multi']}/{baseline['multi_n']}"
        f" tokens {baseline['tokens_mean']:.0f}",
        flush=True,
    )
    outcomes = []
    for point in grid():
        params = to_params(point)
        rows = run_config(ctx, kb, questions, params)
        diff = paired_difference_ci(
            [r["recall"] for r in rows], [r["recall"] for r in baseline_rows]
        )
        outcomes.append(
            {
                "point": point,
                "params": asdict(params),
                "summary": score(rows),
                "vs_A": diff,
                "rows": rows,
            }
        )
    by_key = {_key(o["point"]): o for o in outcomes}
    finalists = {}
    for budget in AXES["budget"]:
        at_budget = [o for o in outcomes if o["point"]["budget"] == budget]
        best = at_budget[0]
        for o in at_budget[1:]:
            if _better(o, best):
                best = o
        chosen, log = ablate(best, by_key)
        finalists[budget] = {
            "best": _key(best["point"]),
            "chosen": _key(chosen["point"]),
            "log": log,
        }
        print(f"\n== budget {budget}\nbest:   {_line(best)}\nchosen: {_line(chosen)}")
        for entry in log:
            print(f"  {entry}")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"stage5_sweep_{stamp}.json"
    slim = [{k: v for k, v in o.items() if k != "rows"} for o in outcomes]
    keep = {k for f in finalists.values() for k in (f["best"], f["chosen"])}
    for o, full in zip(slim, outcomes, strict=True):
        if _key(o["point"]) in keep:
            o["rows"] = full["rows"]
    out.write_text(
        json.dumps(
            {
                "baseline": {"summary": baseline, "rows": baseline_rows},
                "axes": {k: list(v) for k, v in AXES.items()},
                "finalists": {str(k): v for k, v in finalists.items()},
                "configs": slim,
            },
            indent=1,
        )
    )
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
