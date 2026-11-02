# Evaluation report: A (fixed 512/50, top-5) on dev

> **Superseded, not comparable with later reports.** Recall@budget here used 2000 tokens, later reports use 2560. This run also used judge prompt v1 and single-location gold evidence.

- Generated: 2026-10-30T08:44:07+00:00
- Commit: 616e75b+uncommitted
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: gemma4:e4b
- Machine: arm64 Darwin 27.0.0
- Questions: 39 (29 answerable, 10 unanswerable)
- Question source: 39 dev questions; LLM and assistant-written; assistant-reviewed, not human

## Retrieval (answerable questions)

| Metric | Result |
|---|---|
| Recall@budget (2000 tokens), primary | 0.655 (95% CI 0.483–0.828) |
| Recall@5 | 0.759 (95% CI 0.586–0.897) |
| Hit rate@5 | 0.759 (95% CI 0.586–0.897) |
| MRR | 0.564 (95% CI 0.422–0.708) |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 28 / 1 / 0 / 0 |
| Wrong focus: `answered`, no citation on gold evidence | 7 of 28 |
| Wrong focus: `answered`, judge says it misses the question | 0 of 28 |
| Wrong focus: either signal | 7 of 28 |
| Citation precision against gold evidence | 0.589 (95% CI 0.434–0.744) |
| Faithfulness (LLM judge, not ground truth) | 1.000 (95% CI 1.000–1.000) |
| Unanswerable refused by the LLM, gate off | 10 of 10 |
| False answers on unanswerable, gate off | 0 of 10 |
| Generation time p50 / p95 | 36.0 s / 59.7 s |
| Average input / output tokens | 3080 / 107 |
| Generation errors | 0 |
