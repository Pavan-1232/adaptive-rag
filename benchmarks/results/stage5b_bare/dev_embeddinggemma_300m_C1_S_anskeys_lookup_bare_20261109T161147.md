# Evaluation report: S (adaptive retrieval on C1) + answer keys on dev

- Generated: 2026-11-09T16:11:47+00:00
- Commit: 5f425d5+uncommitted
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: none
- Machine: arm64 Darwin 27.2.0
- Questions: 39 (29 answerable, 10 unanswerable)
- Question source: unspecified
- Recall@budget is comparable only between runs with the same token budget.

## Retrieval (answerable questions)

| Metric | Result |
|---|---|
| Recall@budget (2560 tokens), primary | 0.862 (95% CI 0.724–0.966) |
| Recall@5 | 0.862 (95% CI 0.724–0.966) |
| Hit rate@5 | 0.862 (95% CI 0.724–0.966) |
| MRR | 0.661 (95% CI 0.521–0.793) |
| Part coverage (0 questions with 2+ parts) | not measured |
| All parts covered | not measured |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 0 / 0 / 0 / 29 |
| Wrong focus: `answered`, no citation on gold evidence | 0 of 0 |
| Wrong focus: `answered`, judge says it misses the question | 0 of 0 |
| Wrong focus: either signal | 0 of 0 |
| `answered`, gold comparison says conflicts / different point | 0 / 0 of 0 |
| Citation precision against gold evidence | not measured |
| Faithfulness (LLM judge, not ground truth) | not measured |
| Unanswerable refused by the LLM, gate off | 0 of 10 |
| False answers on unanswerable, gate off | 0 of 10 |
| Generation time p50 / p95 | not measured s / not measured s |
| Average input / output tokens | not measured / not measured |
| Generation errors | 0 |

## Notes

Bare titles: adaptive, rule on (lookup on)
