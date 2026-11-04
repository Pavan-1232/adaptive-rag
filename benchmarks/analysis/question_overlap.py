"""Check new dev questions against the held-out test questions for near-duplicates.

Prints and saves IDs and scores only, never test question text, so the test set stays unseen.
Thresholds were fixed before the first run (2026-11-04): flag a pair if content-word Jaccard
on the question is at least 0.5, embedding cosine is at least 0.85, or a quote is identical.

Run from the repo root:
    python benchmarks/analysis/question_overlap.py benchmarks/questions_dev_tables.yaml
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from adaptive_rag.evaluation.__main__ import _providers, _settings
from adaptive_rag.evaluation.benchmark import load_questions
from adaptive_rag.evaluation.questions import _content_words

TEST = Path("benchmarks/questions_test.yaml")
RESULTS = Path("benchmarks/results")
JACCARD_FLAG = 0.5
COSINE_FLAG = 0.85
MODEL = "embeddinggemma:300m"


def jaccard(a: str, b: str) -> float:
    left, right = _content_words(a), _content_words(b)
    return len(left & right) / len(left | right) if left | right else 0.0


def quotes(question) -> set[str]:
    return {
        " ".join(o.quote.lower().split()) for e in question.evidence for o in (e, *e.alternatives)
    }


def main(dev_file: str) -> int:
    dev, test = load_questions(Path(dev_file)), load_questions(TEST)
    embedder, _ = _providers(_settings("dev", MODEL))
    dev_vectors = np.array([embedder.embed_query(q.question) for q in dev])
    test_vectors = np.array([embedder.embed_query(q.question) for q in test])
    dev_vectors /= np.linalg.norm(dev_vectors, axis=1, keepdims=True)
    test_vectors /= np.linalg.norm(test_vectors, axis=1, keepdims=True)
    cosines = dev_vectors @ test_vectors.T

    rows, flagged = [], 0
    for i, question in enumerate(dev):
        j = int(np.argmax(cosines[i]))
        best_jaccard = max(jaccard(question.question, other.question) for other in test)
        shared_quotes = sum(bool(quotes(question) & quotes(other)) for other in test)
        flag = best_jaccard >= JACCARD_FLAG or cosines[i, j] >= COSINE_FLAG or shared_quotes > 0
        flagged += flag
        rows.append(
            {
                "dev_id": question.id,
                "nearest_test_id": test[j].id,
                "cosine": round(float(cosines[i, j]), 3),
                "max_jaccard": round(best_jaccard, 3),
                "identical_quotes": shared_quotes,
                "flagged": flag,
            }
        )
        print(
            f"{question.id:14} nearest {test[j].id:14} cos {cosines[i, j]:.3f} "
            f"jaccard {best_jaccard:.3f} same-quote {shared_quotes} {'FLAG' if flag else ''}"
        )
    print(f"{flagged} of {len(dev)} flagged")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"question_overlap_{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "dev_file": dev_file,
                "test_file": str(TEST),
                "embedding_model": MODEL,
                "thresholds": {"jaccard": JACCARD_FLAG, "cosine": COSINE_FLAG},
                "flagged": flagged,
                "rows": rows,
            },
            indent=2,
        )
    )
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
