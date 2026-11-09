"""Retrieval-only check of a private real-use question set. Prints ranks, never document text.

    python scripts/real_use_retrieval.py data/realuse/ca_questions.yaml data/realuse/ca_index_C1

The YAML (gitignored, under data/) lists questions and, for each, the document and a marker
text that the right chunk contains. The index folder is an app data folder with one knowledge
base. For every setup: the rank of the first right chunk in the candidate pool (top 30), whether
that's in the top 5, and whether it was in the evidence sent to the model.
"""

import argparse
import sys
from pathlib import Path

import yaml

from adaptive_rag.api import build_context
from adaptive_rag.config import code_default_settings
from adaptive_rag.retrieval import retrieve_baseline
from adaptive_rag.retrieval.evidence import retrieve_evidence
from adaptive_rag.vectorstore.process import start_store_process

# Every setup states structured_lookup, so the app default never decides a comparison.
SETUPS = {
    "baseline": {"retrieval": "baseline", "structured_lookup": False},
    "base+lookup": {
        "retrieval": "baseline",
        "structured_lookup": True,
        "lookup_bare_titles": False,
    },
    "adapt+lookup": {
        "retrieval": "adaptive",
        "structured_lookup": True,
        "lookup_bare_titles": False,
    },
    "base+bare": {"retrieval": "baseline", "structured_lookup": True, "lookup_bare_titles": True},
    "adapt+bare": {"retrieval": "adaptive", "structured_lookup": True, "lookup_bare_titles": True},
    "adaptive": {"retrieval": "adaptive", "adaptive_hybrid": False, "structured_lookup": False},
    "hybrid": {"retrieval": "adaptive", "adaptive_hybrid": True, "structured_lookup": False},
    "hyb+phrases": {
        "retrieval": "adaptive",
        "adaptive_hybrid": True,
        "adaptive_keyword_query": "phrases",
        "structured_lookup": False,
    },
    "hyb+bypass": {
        "retrieval": "adaptive",
        "adaptive_hybrid": True,
        "adaptive_keyword_bypass": True,
        "structured_lookup": False,
    },
    "hyb+phr+rrf": {
        "retrieval": "adaptive",
        "adaptive_hybrid": True,
        "adaptive_keyword_query": "phrases",
        "adaptive_fusion": "rrf",
        "structured_lookup": False,
    },
}
POOL = 30


def is_right(chunk, expected) -> bool:
    return any(
        piece.document_id == e["document_id"] and e["marker"] in piece.text
        for piece in chunk.pieces
        for e in expected
    )


def ranked_pool(ctx, kb, question, evidence):
    if ctx.settings.retrieval == "baseline":
        return retrieve_baseline(ctx, kb, question, POOL)
    if ctx.settings.adaptive_hybrid and ctx.settings.adaptive_fusion == "weighted":
        weight = ctx.settings.adaptive_keyword_weight
        return sorted(evidence.candidates, key=lambda c: -(c.score + weight * c.keyword))
    return evidence.candidates  # cosine order, or the fused order with RRF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("questions")
    parser.add_argument("index")
    parser.add_argument("--chunking", default="C1")
    parser.add_argument("--setups", default=",".join(SETUPS))
    args = parser.parse_args()
    setups = {name: SETUPS[name] for name in args.setups.split(",")}

    cases = yaml.safe_load(Path(args.questions).read_text())["questions"]
    ctx = build_context(code_default_settings(data_dir=Path(args.index), chunking=args.chunking))
    process, ctx.store = start_store_process(ctx.settings.chroma_dir)
    base = ctx.settings.model_copy()
    try:
        with ctx.db() as conn:
            kb = conn.execute("SELECT * FROM knowledge_bases ORDER BY id LIMIT 1").fetchone()
            ids = {
                r["filename"]: r["id"] for r in conn.execute("SELECT id, filename FROM documents")
            }
        for case in cases:
            for e in case["expected"]:
                e["document_id"] = ids[e["document"]]

        print(f"{'question':30}" + "".join(f"{name:>13}" for name in setups))
        totals = {name: [0, 0] for name in setups}
        for case in cases:
            row = f"{case['id'][:30]:30}"
            for name, overrides in setups.items():
                ctx.settings = base.model_copy(update=overrides)
                evidence = retrieve_evidence(ctx, kb, case["question"])
                pool = ranked_pool(ctx, kb, case["question"], evidence)
                rank = next(
                    (i + 1 for i, c in enumerate(pool) if is_right(c, case["expected"])), None
                )
                sent = any(is_right(c, case["expected"]) for c in evidence.used)
                totals[name][0] += bool(rank and rank <= 5)
                totals[name][1] += sent
                cell = f"{rank or '-'} {'sent' if sent else '----'}"
                row += f"{cell:>13}"
            print(row)
        print(
            f"{'top 5 / sent':30}" + "".join(f"{f'{t[0]} / {t[1]}':>13}" for t in totals.values())
        )
    finally:
        process.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
