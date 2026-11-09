# Evaluation report: S (adaptive retrieval on C1) + answer keys on dev

- Generated: 2026-11-09T16:11:41+00:00
- Commit: 5f425d5+uncommitted
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: none
- Machine: arm64 Darwin 27.2.0
- Questions: 12 (12 answerable, 0 unanswerable)
- Question source: unspecified
- Recall@budget is comparable only between runs with the same token budget.

## Retrieval (answerable questions)

| Metric | Result |
|---|---|
| Recall@budget (2560 tokens), primary | 0.810 (95% CI 0.706–0.914) |
| Recall@5 | 0.810 (95% CI 0.706–0.914) |
| Hit rate@5 | 1.000 (95% CI 1.000–1.000) |
| MRR | 0.785 (95% CI 0.604–0.944) |
| Part coverage (12 questions with 2+ parts) | 0.750 (95% CI 0.625–0.875) |
| All parts covered | 0.417 (95% CI 0.167–0.667) |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 0 / 0 / 0 / 12 |
| Wrong focus: `answered`, no citation on gold evidence | 0 of 0 |
| Wrong focus: `answered`, judge says it misses the question | 0 of 0 |
| Wrong focus: either signal | 0 of 0 |
| `answered`, gold comparison says conflicts / different point | 0 / 0 of 0 |
| Citation precision against gold evidence | not measured |
| Faithfulness (LLM judge, not ground truth) | not measured |
| Unanswerable refused by the LLM, gate off | 0 of 0 |
| False answers on unanswerable, gate off | 0 of 0 |
| Generation time p50 / p95 | not measured s / not measured s |
| Average input / output tokens | not measured / not measured |
| Generation errors | 0 |

## Notes

Bare titles: adaptive, rule off (lookup on)
