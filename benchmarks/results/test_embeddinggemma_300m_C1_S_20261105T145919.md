# Evaluation report: S (adaptive retrieval on C1) on test

- Generated: 2026-11-05T14:59:19+00:00
- Commit: 378783b
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: gemma4:e4b
- Machine: arm64 Darwin 27.2.0
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
| Part coverage (6 questions with 2+ parts) | 0.750 (95% CI 0.417–1.000) |
| All parts covered | 0.667 (95% CI 0.333–1.000) |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 24 / 0 / 0 / 0 |
| Wrong focus: `answered`, no citation on gold evidence | 3 of 24 |
| Wrong focus: `answered`, judge says it misses the question | 2 of 24 |
| Wrong focus: either signal | 5 of 24 |
| `answered`, gold comparison says conflicts / different point | 2 / 0 of 24 |
| Citation precision against gold evidence | 0.753 (95% CI 0.597–0.889) |
| Faithfulness (LLM judge, not ground truth) | 0.924 (95% CI 0.847–0.986) |
| Unanswerable refused by the LLM, gate off | 6 of 6 |
| False answers on unanswerable, gate off | 0 of 6 |
| Generation time p50 / p95 | 31.5 s / 36.2 s |
| Average input / output tokens | 2894 / 88 |
| Generation errors | 0 |

## Notes

Stage 5 pre-registered held-out run (decision 56)
