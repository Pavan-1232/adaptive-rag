# Evaluation report: C7 (table-aware 512/50, top-5) on test

- Generated: 2026-11-04T08:12:08+00:00
- Commit: b386cd9+uncommitted
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
| Recall@5 | 0.818 (95% CI 0.664–0.958) |
| Hit rate@5 | 0.833 (95% CI 0.667–0.958) |
| MRR | 0.643 (95% CI 0.505–0.778) |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 23 / 0 / 1 / 0 |
| Wrong focus: `answered`, no citation on gold evidence | 3 of 23 |
| Wrong focus: `answered`, judge says it misses the question | 2 of 23 |
| Wrong focus: either signal | 5 of 23 |
| `answered`, gold comparison says conflicts / different point | 2 / 0 of 23 |
| Citation precision against gold evidence | 0.726 (95% CI 0.565–0.870) |
| Faithfulness (LLM judge, not ground truth) | 0.909 (95% CI 0.801–0.986) |
| Unanswerable refused by the LLM, gate off | 6 of 6 |
| False answers on unanswerable, gate off | 0 of 6 |
| Generation time p50 / p95 | 32.3 s / 40.1 s |
| Average input / output tokens | 2516 / 90 |
| Generation errors | 0 |

## Notes

Stage 4 pre-registered held-out run (decision 42)
