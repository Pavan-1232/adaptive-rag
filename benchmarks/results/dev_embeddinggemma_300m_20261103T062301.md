# Evaluation report: A (fixed 512/50, top-5) on dev

- Generated: 2026-11-03T06:23:01+00:00
- Commit: d69ee36+uncommitted
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: gemma4:e4b
- Machine: arm64 Darwin 27.0.0
- Questions: 39 (29 answerable, 10 unanswerable)
- Question source: 39 dev questions; LLM and assistant-written; assistant-reviewed, not human
- Recall@budget is comparable only between runs with the same token budget.

## Retrieval (answerable questions)

| Metric | Result |
|---|---|
| Recall@budget (2560 tokens), primary | 0.862 (95% CI 0.724–0.966) |
| Recall@5 | 0.862 (95% CI 0.724–0.966) |
| Hit rate@5 | 0.862 (95% CI 0.724–0.966) |
| MRR | 0.661 (95% CI 0.521–0.793) |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 28 / 1 / 0 / 0 |
| Wrong focus: `answered`, no citation on gold evidence | 3 of 28 |
| Wrong focus: `answered`, judge says it misses the question | 0 of 28 |
| Wrong focus: either signal | 3 of 28 |
| `answered`, gold comparison says conflicts / different point | 2 / 0 of 28 |
| Citation precision against gold evidence | 0.710 (95% CI 0.569–0.839) |
| Faithfulness (LLM judge, not ground truth) | 0.915 (95% CI 0.849–0.970) |
| Unanswerable refused by the LLM, gate off | 10 of 10 |
| False answers on unanswerable, gate off | 0 of 10 |
| Generation time p50 / p95 | 37.5 s / 48.8 s |
| Average input / output tokens | 3080 / 107 |
| Generation errors | 0 |

## Notes

Recall@budget uses 2560 tokens and gold evidence allows alternatives, so it is not comparable with earlier reports. Judge: audit prompt with code check, plus gold comparison.
