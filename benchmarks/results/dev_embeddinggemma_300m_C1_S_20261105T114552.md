# Evaluation report: S (adaptive retrieval on C1) on dev

- Generated: 2026-11-05T11:45:52+00:00
- Commit: e4fd733+uncommitted
- Embedding model: embeddinggemma:300m (85462619ee72)
- LLM: qwen3.5:9b; judge: gemma4:e4b
- Machine: arm64 Darwin 27.0.0
- Questions: 15 (15 answerable, 0 unanswerable)
- Question source: claude-separate-session, user spot-checked (decision 34)
- Recall@budget is comparable only between runs with the same token budget.

## Retrieval (answerable questions)

| Metric | Result |
|---|---|
| Recall@budget (2560 tokens), primary | 0.800 (95% CI 0.600–1.000) |
| Recall@5 | 0.800 (95% CI 0.600–1.000) |
| Hit rate@5 | 0.800 (95% CI 0.600–1.000) |
| MRR | 0.478 (95% CI 0.312–0.652) |
| Part coverage (0 questions with 2+ parts) | not measured |
| All parts covered | not measured |

## Answers

| Metric | Result |
|---|---|
| Answerable marked answered / partial / insufficient / no result | 11 / 4 / 0 / 0 |
| Wrong focus: `answered`, no citation on gold evidence | 0 of 11 |
| Wrong focus: `answered`, judge says it misses the question | 1 of 11 |
| Wrong focus: either signal | 1 of 11 |
| `answered`, gold comparison says conflicts / different point | 1 / 0 of 11 |
| Citation precision against gold evidence | 0.656 (95% CI 0.433–0.856) |
| Faithfulness (LLM judge, not ground truth) | 0.772 (95% CI 0.589–0.928) |
| Unanswerable refused by the LLM, gate off | 0 of 0 |
| False answers on unanswerable, gate off | 0 of 0 |
| Generation time p50 / p95 | 33.1 s / 38.5 s |
| Average input / output tokens | 3060 / 85 |
| Generation errors | 0 |

## Notes

Stage 5 table-prompt test, finalist S from stage5_sweep_20261105T114432
