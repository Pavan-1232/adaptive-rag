"""For the three real failures, change one thing at a time and see if the answer recovers."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from adaptive_rag.answering.prompts import ANSWER_SCHEMA, build_messages
from adaptive_rag.evaluation.__main__ import DOCUMENTS, _providers, _settings
from adaptive_rag.evaluation.benchmark import load_manifest, load_questions
from adaptive_rag.evaluation.runner import build_index, evidence_spans
from adaptive_rag.retrieval import retrieve_baseline

STRICT_RULE = (
    "\n- Before using a figure or fact, check that the evidence is about the same entity, metric, "
    "period and scope as the question. A table row whose title is missing, or a fact about a "
    'subset or a related topic, does not answer the question: use "partial" or "insufficient" '
    "rather than presenting it as the answer."
)
# Passages cut by hand, as a stand-in for chunks that keep a table with its title.
TIGHT = {
    "tesla-a1": ("Research and Development Expense", "As a percentage of revenues 5 % 4 % 4 %"),
    "tesla-a3": ("Consolidated Balance Sheets", "Total current assets 58,360 49,616"),
    "nist_ai_rmf-gen-015": None,
}
# The retrieved chunk that misled the answer, whose preceding chunk holds the table's title.
MISLEADING = {
    "tesla-a1": "Research and development 832",
    "tesla-a3": "Cash and cash equivalents $ 49",
}


def main():
    settings = _settings("dev", "embeddinggemma:300m")
    embedder, llm = _providers(settings)
    ctx, kb, indexed = build_index(
        settings, embedder, llm, load_manifest(split="dev"), DOCUMENTS, "benchmark-dev"
    )
    questions = {q.id: q for q in load_questions(Path("benchmarks/questions_dev.yaml"))}
    rows = []
    for qid in TIGHT:
        q = questions[qid]
        doc = indexed[q.document]
        span = evidence_spans(q, indexed)[0]
        pool = retrieve_baseline(ctx, kb, q.question, 30)
        top5 = pool[:5]
        by_range = {(c.start_char, c.end_char): c for c in pool}
        gold = next((c for c in pool if c.start_char < span.end and c.end_char > span.start), None)
        if gold is None:
            with ctx.db() as conn:
                row = conn.execute(
                    "SELECT start_char, end_char, text FROM chunks WHERE document_id = ? AND"
                    " start_char < ? AND end_char > ? ORDER BY start_char LIMIT 1",
                    (doc["id"], span.end, span.start),
                ).fetchone()
            gold = replace(
                top5[0], text=row["text"], start_char=row["start_char"], end_char=row["end_char"]
            )
        variants = {"baseline": (top5, "")}
        variants["retrieval: gold chunk replaces rank 5"] = (top5[:4] + [gold], "")
        variants["prompt: stricter rule, same evidence"] = (top5, STRICT_RULE)
        if qid in MISLEADING:
            target = next(c for c in top5 if MISLEADING[qid] in c.text)
            with ctx.db() as conn:
                previous = conn.execute(
                    "SELECT text FROM chunks WHERE document_id = ? AND end_char <= ? + 400"
                    " AND start_char < ? ORDER BY start_char DESC LIMIT 1",
                    (doc["id"], target.start_char, target.start_char),
                ).fetchone()["text"]
            widened = [
                replace(c, text=previous + "\n" + c.text) if c is target else c for c in top5
            ]
            variants["chunking: misleading chunk keeps table title"] = (widened, "")
            rows.append({"id": qid, "text_added_before_chunk_tail": previous[-500:]})
            print(qid, "ADDED TAIL:", previous[-500:], flush=True)
        for name, (chunks, rule) in variants.items():
            messages = build_messages(q.question, chunks)
            messages[0] = {"role": "system", "content": messages[0]["content"] + rule}
            result = llm.generate(
                messages, schema=ANSWER_SCHEMA, max_tokens=settings.max_answer_tokens
            )
            rows.append({"id": qid, "variant": name, "output": json.loads(result.text)})
            print(qid, "|", name, "|", result.text[:400], flush=True)

        text = doc["canonical_text"]
        if TIGHT[qid]:
            start_marker, end_marker = TIGHT[qid]
            start = text.index(start_marker, max(0, span.start - 800))
            end = text.index(end_marker, start) + len(end_marker)
            passage = text[start:end]
        else:
            passage = text[span.start : span.end]
        vector = np.array(embedder.embed_documents([passage], [Path(q.document).stem])[0])
        query = np.array(embedder.embed_query(q.question))
        score = float(vector @ query / (np.linalg.norm(vector) * np.linalg.norm(query)))
        rank = 1 + sum(c.score > score for c in pool)
        rows.append(
            {
                "id": qid,
                "tight_passage_chars": len(passage),
                "tight_score": score,
                "would_rank": rank,
                "rank1_score": pool[0].score,
                "gold_chunk_rank": next(
                    (
                        n + 1
                        for n, c in enumerate(pool)
                        if (c.start_char, c.end_char) in by_range
                        and c.start_char < span.end
                        and c.end_char > span.start
                    ),
                    None,
                ),
            }
        )
        print(qid, rows[-1], flush=True)
    llm.unload()
    path = Path("benchmarks/results") / f"cause_experiment_{datetime.now(UTC):%Y%m%dT%H%M%S}.json"
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print("wrote", path)


if __name__ == "__main__":
    main()
