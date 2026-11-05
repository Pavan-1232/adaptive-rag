"""Stage 5 retrieval-only sweep on dev. No LLM calls; query embeddings are cached.

Usage: python benchmarks/analysis/stage5_sweep.py

Scores each AdaptiveParams config on the 56 answerable dev questions (dev, dev tables, dev
multi-part) by recall over the evidence actually sent, part coverage and tokens sent, and
compares with A (top-5, 2560 tokens). Writes benchmarks/results/stage5_sweep_<stamp>.json.

Selection rule, fixed before the first run (PROGRESS.md decision 49): highest mean recall
sent; a feature stays on only if switching it off lowers recall sent or part coverage.
"""

import itertools
import json
import sys
from dataclasses import asdict
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
    questions = []
    for name in FILES:
        for question in load_questions(Path("benchmarks") / name):
            if question.answerable:
                questions.append((name, question, evidence_spans(question, indexed)))
    return ctx, kb, questions


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
        rows.append(_row(name, question, spans, result.chunks, result.duplicate_tokens))
    return rows


def _row(name, question, spans, used, duplicate_tokens=0) -> dict:
    sent = _ranked(used)
    return {
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


def grid() -> list[AdaptiveParams]:
    configs = []
    for budget, split, delta, multi_max, dedupe, neighbors in itertools.product(
        (2500, 2560, 4000),
        (False, True),
        (None, 0.05, 0.10, 0.15),
        (5, 8),
        (False, True),
        (False, True),
    ):
        configs.append(
            AdaptiveParams(
                budget=budget,
                split_parts=split,
                delta=delta,
                max_chunks={"factual": 5, "table": 5, "multi_part": multi_max, "broad": 10},
                dedupe=dedupe,
                neighbors=neighbors,
            )
        )
    return configs


def main() -> int:
    ctx, kb, questions = load_dev()
    baseline_rows = run_baseline(ctx, kb, questions)
    baseline = score(baseline_rows)
    print(
        f"A: recall {baseline['recall_sent'][0]:.3f} parts {baseline['part_coverage_multi'][0]:.3f}"
        f" all-parts {baseline['all_parts_multi']}/{baseline['multi_n']}"
        f" tokens {baseline['tokens_mean']:.0f}"
    )
    outcomes = []
    for params in grid():
        rows = run_config(ctx, kb, questions, params)
        summary = score(rows)
        diff = paired_difference_ci(
            [r["recall"] for r in rows], [r["recall"] for r in baseline_rows]
        )
        outcomes.append({"params": asdict(params), "summary": summary, "vs_A": diff, "rows": rows})
    outcomes.sort(key=lambda o: -o["summary"]["recall_sent"][0])
    for o in outcomes[:15]:
        p, s = o["params"], o["summary"]
        print(
            f"b{p['budget']} split={p['split_parts']:d} d={p['delta']}"
            f" mmax={p['max_chunks']['multi_part']}"
            f" dedupe={p['dedupe']:d} nb={p['neighbors']:d} | recall {s['recall_sent'][0]:.3f}"
            f" tbl {s['recall_sent_tables'][0]:.3f} parts {s['part_coverage_multi'][0]:.3f}"
            f" all {s['all_parts_multi']}/{s['multi_n']} tok {s['tokens_mean']:.0f}"
            f" | vs A {o['vs_A'][0]:+.3f} ({o['vs_A'][1]:+.3f},{o['vs_A'][2]:+.3f})"
        )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"stage5_sweep_{stamp}.json"
    out.write_text(
        json.dumps(
            {"baseline": {"summary": baseline, "rows": baseline_rows}, "configs": outcomes},
            indent=1,
        )
    )
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
