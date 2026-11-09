"""Run the chunking optimizer on each dev document and measure the ingest time it adds.

Embeddings are NOT cached here, so the timings are what a real first ingest costs. Per
document: extraction, full optimization (questions, unload, candidates), and indexing the
winner over the whole document. Results are saved per document, so a stopped run can skip
documents already done.

Run from the repo root: python benchmarks/analysis/optimize_dev.py [results_dir]
"""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from adaptive_rag.chunking import embedding_text
from adaptive_rag.config import code_default_settings
from adaptive_rag.evaluation.__main__ import DOCUMENTS
from adaptive_rag.evaluation.benchmark import load_manifest
from adaptive_rag.loaders import LOADERS
from adaptive_rag.optimizer.candidates import BY_ID, build_chunks
from adaptive_rag.optimizer.optimize import Caps, optimize_document
from adaptive_rag.providers import OllamaEmbeddings, OllamaLLM

MODEL = "embeddinggemma:300m"


def git_commit() -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)  # noqa: S607
    return out.stdout.strip()


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_dir = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(f"benchmarks/results/optimize_dev_{stamp}")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = code_default_settings()
    embedder = OllamaEmbeddings(MODEL, settings.ollama_host, settings.embedding_batch_size)
    llm = OllamaLLM(settings.llm_model, settings.ollama_host, settings.num_ctx)
    for item in load_manifest(split="dev"):
        path = out_dir / f"{item.name.rsplit('.', 1)[0]}.json"
        if path.exists():
            print(f"{item.name}: already done", flush=True)
            continue
        t = time.monotonic()
        doc = LOADERS["pdf"].extract(DOCUMENTS / item.file)
        extract_s = time.monotonic() - t

        result = optimize_document(doc, item.name, "pdf", embedder, llm, Caps())

        # Index the winner over the whole document, as ingestion would, cold.
        title = item.name.rsplit(".", 1)[0]
        t = time.monotonic()
        chunks = build_chunks(BY_ID[result.winner], doc, embedder, title)
        vectors = embedder.embed_documents(
            [embedding_text(doc.text, c) for c in chunks], [title] * len(chunks)
        )
        index_s = time.monotonic() - t
        assert len(np.asarray(vectors)) == len(chunks)

        record = result.to_dict()
        record["ingest_timings_s"] = {
            "extract": round(extract_s, 2),
            "optimize": result.timings_s["total"],
            "index_winner": round(index_s, 2),
            "total": round(extract_s + result.timings_s["total"] + index_s, 2),
        }
        record["winner_chunks_full_document"] = len(chunks)
        record["meta"] = {
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": git_commit(),
            "embedding_model": MODEL,
            "embedding_digest": embedder.version(),
            "llm_model": settings.llm_model,
            "embeddings_cached": False,
        }
        path.write_text(json.dumps(record, indent=2))
        print(
            f"{item.name}: winner {result.winner} ({result.winner_reason}); "
            f"questions {result.questions_selection}+{result.questions_confirmation}; "
            f"ingest {record['ingest_timings_s']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
