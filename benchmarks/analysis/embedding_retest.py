"""Stage 4 retest of bge-m3:latest against embeddinggemma:300m, dev documents only.

Procedure and decision rule were fixed in docs/PROGRESS.md (Stage 4, step 4) before this ran.
Retrieval only, in memory: all 4 dev documents in one pool, exact cosine, pool 30, Recall@budget
at 2560 evidence tokens. Grid: two embedding models x chunking configs C1, C3, C7.

Run from the repo root: python benchmarks/analysis/embedding_retest.py
"""

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.evaluation.__main__ import DOCUMENTS
from adaptive_rag.evaluation.benchmark import load_manifest, load_questions
from adaptive_rag.evaluation.stats import mean_ci, paired_difference_ci
from adaptive_rag.loaders import LOADERS
from adaptive_rag.optimizer.candidates import BY_ID, build_chunks
from adaptive_rag.optimizer.embcache import CachedEmbeddings
from adaptive_rag.optimizer.scoring import (
    RECALL_BUDGET_TOKENS,
    DocumentChunks,
    InMemoryIndex,
    question_spans,
    score_question,
)
from adaptive_rag.providers import OllamaEmbeddings

RESULTS = Path("benchmarks/results")
CACHE = Path("data/eval/embcache")
MODELS = ("embeddinggemma:300m", "bge-m3:latest")
CONFIGS = ("C1", "C3", "C7")
QUESTION_FILES = ("benchmarks/questions_dev.yaml", "benchmarks/questions_dev_tables.yaml")
EXTRACTION_FAILURES = {"tbl-nist-01", "tbl-nist-04"}
HOST = "http://127.0.0.1:11434"


def subsets(questions) -> dict[str, list[str]]:
    table = [q.id for q in questions if q.type == "table"]
    return {
        "all": [q.id for q in questions],
        "table_clean": [i for i in table if i not in EXTRACTION_FAILURES],
        "table_extraction_failures": [i for i in table if i in EXTRACTION_FAILURES],
        "non_table": [q.id for q in questions if q.type != "table"],
    }


def git_state() -> dict:
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout  # noqa: S607
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)  # noqa: S607
    dirty = dirty.stdout
    return {"commit": head.strip(), "uncommitted_changes": bool(dirty.strip())}


def main() -> int:
    manifest = load_manifest(split="dev")
    docs = {item.name: LOADERS["pdf"].extract(DOCUMENTS / item.file) for item in manifest}
    questions = [q for f in QUESTION_FILES for q in load_questions(Path(f)) if q.answerable]
    spans = {q.id: question_spans(q, docs[q.document]) for q in questions}
    groups = subsets(questions)

    scores: dict[str, dict[str, dict]] = {}
    meta: dict[str, dict] = {}
    for model in MODELS:
        raw = OllamaEmbeddings(model, HOST, 32)
        embedder = CachedEmbeddings(raw, CACHE / f"{model.replace(':', '_')}.sqlite")
        meta[model] = {"digest": embedder.version(), "prompt_version": raw.prompt_version}
        t = time.monotonic()
        query_vectors = {q.id: embedder.embed_query(q.question) for q in questions}
        meta[model]["query_seconds"] = round(time.monotonic() - t, 2)
        for config in CONFIGS:
            candidate = BY_ID[config]
            parts = []
            for name, doc in docs.items():
                title = name.rsplit(".", 1)[0]
                parts.append(DocumentChunks(name, doc, build_chunks(candidate, doc), title))
            misses_before = embedder.misses
            t = time.monotonic()
            index = InMemoryIndex(parts, embedder)
            seconds = time.monotonic() - t
            key = f"{model}|{config}"
            meta[key] = {
                "chunks": len(index.ranked),
                "storage_tokens": index.storage_tokens,
                "index_seconds": round(seconds, 2),
                "newly_embedded": embedder.misses - misses_before,
            }
            scores[key] = {
                q.id: vars(score_question(index, query_vectors[q.id], q.id, spans[q.id]))
                for q in questions
            }
            print(f"{key}: {len(index.ranked)} chunks, index {seconds:.1f}s", flush=True)

    summary: dict[str, dict] = {}
    for config in CONFIGS:
        gemma, bge = (scores[f"{m}|{config}"] for m in MODELS)
        row: dict[str, dict] = {}
        for group, ids in groups.items():
            if not ids:
                continue
            row[group] = {"n": len(ids)}
            for metric in ("recall_at_budget", "hit_at_5", "reciprocal_rank"):
                a = [gemma[i][metric] for i in ids]
                b = [bge[i][metric] for i in ids]
                row[group][metric] = {
                    "embeddinggemma": mean_ci(a),
                    "bge_m3": mean_ci(b),
                    "difference_bge_minus_gemma": paired_difference_ci(b, a),
                }
        table_low = row["table_clean"]["recall_at_budget"]["difference_bge_minus_gemma"][1]
        overall_high = row["all"]["recall_at_budget"]["difference_bge_minus_gemma"][2]
        row["favours_bge_m3"] = bool(table_low > 0 and overall_high >= 0)
        summary[config] = row
    favour = sum(summary[c]["favours_bge_m3"] for c in CONFIGS)
    decision = "switch to bge-m3:latest" if favour >= 2 else "keep embeddinggemma:300m"

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"embedding_retest_{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "created": stamp,
                "git": git_state(),
                "budget_tokens": RECALL_BUDGET_TOKENS,
                "question_files": QUESTION_FILES,
                "extraction_failures": sorted(EXTRACTION_FAILURES),
                "subsets": groups,
                "meta": meta,
                "summary": summary,
                "configs_favouring_bge_m3": favour,
                "decision_by_rule": decision,
                "per_question": scores,
            },
            indent=2,
        )
    )
    print(f"configs favouring bge-m3: {favour} of {len(CONFIGS)} -> {decision}")
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
