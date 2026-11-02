"""Extra floor probes (scores only, no LLM) and how results move if narrow gold is widened.

Historical: run before evidence alternatives and the 2560-token budget. Its saved output used a
2000-token budget and single-location gold, so rerunning it now won't reproduce those columns.
"""

import json
from pathlib import Path

import numpy as np

from adaptive_rag.evaluation.__main__ import DOCUMENTS, _providers, _settings
from adaptive_rag.evaluation.benchmark import load_manifest, load_questions
from adaptive_rag.evaluation.metrics import (
    RankedChunk,
    Span,
    hit_at_k,
    recall_at_budget,
    reciprocal_rank,
)
from adaptive_rag.evaluation.runner import build_index, evidence_spans
from adaptive_rag.evaluation.spans import locate_quote
from adaptive_rag.evaluation.stats import is_tie, paired_difference_ci
from adaptive_rag.retrieval import retrieve_baseline

MODELS = ["embeddinggemma:300m", "bge-m3:latest"]
OUT_OF_SCOPE = [
    "What is the capital of Australia?",
    "How do I bake banana bread?",
    "Who won the 2018 FIFA World Cup?",
    "What is the speed of light?",
    "How many bones are in the human body?",
    "What is photosynthesis?",
    "Recommend a good hiking trail in Colorado.",
    "How do I change a flat bicycle tyre?",
    "Who wrote Pride and Prejudice?",
    "What is the tallest mountain in Africa?",
    "How do vaccines train the immune system?",
    "What are the rules of cricket?",
    "How often should I water a cactus?",
    "What is the plot of Hamlet?",
    "When did the Roman Empire fall?",
]
TERSE_ANSWERABLE = [
    "Tesla R&D 2024",
    "Tesla auditor",
    "Tesla net income 2024",
    "Gigafactory Berlin",
    "insider trading blackout",
    "Is the framework voluntary?",
    "What does GOVERN do?",
    "AI RMF Core functions",
    "risk tolerance",
    "trustworthy AI characteristics",
    "faithfulness definition",
    "WikiEval size",
    "context relevance",
    "What is Ragas?",
    "answer relevance score",
]
# Passages that also answer the question. Listed from the documents, for either retriever.
ALTERNATES = {
    "tesla-a4": [("tesla_10k.pdf", "Automotive sales revenue decreased $6.03 billion, or 8%")],
    "tesla-a1": [("tesla_10k.pdf", "Research and development 4,540 3,969 3,075")],
    "tesla-a2": [],
    "nist-a1": [("nist_ai_rmf.pdf", "It describes four specific functions")],
    "ragas-gen-000": [("ragas.pdf", "fully self-contained and reference-free")],
    "ragas-gen-010": [("ragas.pdf", "can be inferred from the context")],
}


def main():
    questions = load_questions(Path("benchmarks/questions_dev.yaml"))
    metrics = {}
    probes = {}
    for model in MODELS:
        settings = _settings("dev", model)
        embedder, llm = _providers(settings)
        ctx, kb, indexed = build_index(
            settings, embedder, llm, load_manifest(split="dev"), DOCUMENTS, "benchmark-dev"
        )
        probes[model] = {
            "out_of_scope": {q: retrieve_baseline(ctx, kb, q, 1)[0].score for q in OUT_OF_SCOPE},
            "terse_answerable": {
                q: retrieve_baseline(ctx, kb, q, 1)[0].score for q in TERSE_ANSWERABLE
            },
        }
        rows = {}
        for q in questions:
            if not q.answerable:
                continue
            pool = retrieve_baseline(ctx, kb, q.question, 30)
            ranked = [
                RankedChunk(c.filename, c.start_char, c.end_char, c.token_count) for c in pool
            ]
            options = [evidence_spans(q, indexed)]
            for document, quote in ALTERNATES.get(q.id, []):
                found = locate_quote(indexed[document]["canonical_text"], quote)
                assert found, quote
                options.append([Span(document, *found)])
            rows[q.id] = {
                "type": q.type,
                "document": q.document,
                "strict_budget": recall_at_budget(ranked, options[0], 2000),
                "strict_hit5": hit_at_k(ranked, options[0], 5),
                "strict_rr": reciprocal_rank(ranked, options[0]),
                "wide_budget": max(recall_at_budget(ranked, o, 2000) for o in options),
                "wide_hit5": max(hit_at_k(ranked, o, 5) for o in options),
                "wide_rr": max(reciprocal_rank(ranked, o) for o in options),
                "budget_2560": recall_at_budget(ranked, options[0], 2560),
            }
        metrics[model] = rows
        print(
            model,
            {
                k: round(float(np.mean([r[k] for r in rows.values()])), 3)
                for k in next(iter(rows.values()))
                if k not in ("type", "document")
            },
        )
        for group in ("table", "factual", "conceptual", "multi_part"):
            chosen = [r for r in rows.values() if r["type"] == group]
            print(
                " ",
                group,
                len(chosen),
                round(float(np.mean([r["strict_hit5"] for r in chosen])), 3),
            )
        for doc in ("tesla_10k.pdf", "nist_ai_rmf.pdf", "ragas.pdf"):
            chosen = [r for r in rows.values() if r["document"] == doc]
            print(
                " ",
                doc,
                len(chosen),
                round(float(np.mean([r["strict_budget"] for r in chosen])), 3),
            )
        for kind, values in probes[model].items():
            scores = sorted(values.values())
            print(
                " ",
                kind,
                "min",
                round(scores[0], 3),
                "median",
                round(float(np.median(scores)), 3),
                "max",
                round(scores[-1], 3),
            )
            print(
                "   lowest/highest:", min(values, key=values.get), "/", max(values, key=values.get)
            )
    first, second = metrics[MODELS[1]], metrics[MODELS[0]]
    ids = sorted(first)
    for key in ("strict_budget", "strict_hit5", "strict_rr", "wide_budget", "wide_hit5", "wide_rr"):
        ci = paired_difference_ci([first[i][key] for i in ids], [second[i][key] for i in ids])
        print(
            f"bge minus gemma {key}: {ci[0]:+.3f} ({ci[1]:+.3f} to {ci[2]:+.3f})",
            "tie" if is_tie(ci) else "different",
        )
    print("question-level strict hit@5 changes (gemma -> bge):")
    for i in ids:
        if first[i]["strict_hit5"] != second[i]["strict_hit5"]:
            print(" ", i, second[i]["strict_hit5"], "->", first[i]["strict_hit5"])
    Path("benchmarks/results/floor_and_gold_sensitivity_20261102.json").write_text(
        json.dumps({"probes": probes, "metrics": metrics}, indent=1, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
