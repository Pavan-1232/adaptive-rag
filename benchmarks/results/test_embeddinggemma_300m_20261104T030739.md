# Evaluation report: A (fixed 512/50, top-5) on test

- Generated: 2026-11-04T03:07:39+00:00
- Commit: e366498+uncommitted
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: gemma4:e4b
- Machine: arm64 Darwin 27.0.0
- Questions: 30 (24 answerable, 6 unanswerable)
- Question source: 30 test questions written by Claude in a separate chat session; 5 spot-checked against the PDFs by the user; not human-written
- Recall@budget is comparable only between runs with the same token budget.

## Retrieval (answerable questions)

| Metric | Result |
|---|---|
| Recall@budget (2560 tokens), primary | 0.860 (95% CI 0.708–0.985) |
| Recall@5 | 0.860 (95% CI 0.708–0.985) |
| Hit rate@5 | 0.875 (95% CI 0.750–1.000) |
| MRR | 0.716 (95% CI 0.572–0.850) |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 23 / 1 / 0 / 0 |
| Wrong focus: `answered`, no citation on gold evidence | 3 of 23 |
| Wrong focus: `answered`, judge says it misses the question | 2 of 23 |
| Wrong focus: either signal | 5 of 23 |
| `answered`, gold comparison says conflicts / different point | 2 / 0 of 23 |
| Citation precision against gold evidence | 0.750 (95% CI 0.583–0.896) |
| Faithfulness (LLM judge, not ground truth) | 0.882 (95% CI 0.771–0.965) |
| Unanswerable refused by the LLM, gate off | 6 of 6 |
| False answers on unanswerable, gate off | 0 of 6 |
| Generation time p50 / p95 | 33.7 s / 40.3 s |
| Average input / output tokens | 3152 / 87 |
| Generation errors | 0 |

## Notes

Held-out test run for Stage 3, run once. Judge: audit-1 prompt, loose-1 code check (tuned on dev), plus gold comparison. Recall@budget uses 2560 tokens.
