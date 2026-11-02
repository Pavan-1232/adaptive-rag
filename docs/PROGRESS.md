# Adaptive RAG: Progress

**Last updated:** 2026-11-02
**Current state:** Stage 3 in progress and paused at the user's request. All user decisions are implemented in code and the work so far is in a WIP checkpoint commit on branch `stage-3-evaluation-harness`. The dev report rerun was stopped partway and saved no results, so it must be run again, followed by the audit false-alarm check. See "Next steps". Numbers under "Stage 3 results so far" come from the old setup unless marked otherwise.

The approved architecture is in [DESIGN.md](DESIGN.md).

## Stage status

| Stage | Name | Status |
|---|---|---|
| 1 | Design | Complete; approved 2026-10-30 |
| 2 | Baseline backend | Complete and committed 2026-10-30 |
| 3 | Evaluation harness | In progress; dev work done, decisions and test questions outstanding |
| 4 | Chunking optimization | Not started |
| 5 | Adaptive retrieval | Not started |
| 6 | BYOK | Not started |
| 7 | Frontend | Not started |
| 8 | GitHub polish | Not started |

## Decisions taken

| # | Decision | Date |
|---|---|---|
| 1 | Recall@budget is the primary chunking metric | 2026-10-30 |
| 2 | Citation locators are format-specific: PDF page, DOCX section and paragraph range, TXT section and line range | 2026-10-30 |
| 3 | `pdfplumber` for PDF extraction | 2026-10-30 |
| 4 | Public benchmark from SEC 10-K filings, CC-BY arXiv papers, and government reports | 2026-10-30 |
| 5 | Start with about 30 human-written questions; grow later | 2026-10-30 |
| 6 | New conda env `adaptive-rag` on Python 3.11; leave `rag-env` untouched | 2026-10-30 |
| 7 | `git init` at the start of Stage 2, with `.gitignore` first; commit only when asked | 2026-10-30 |
| 8 | MIT licence; final decision at Stage 8 | 2026-10-30 |
| 9 | If the smoke test shows question generation is slow, flag it and propose a lower question count before Stage 4 | 2026-10-30 |
| 10 | Keep the 40-question limit per document; generation was not slow | 2026-10-30 |
| 11 | `think=False` is required for all generation | 2026-10-30 |
| 12 | Default evidence target lowered from 4,000 to 2,500 tokens; 4,000 is the maximum | 2026-10-30 |
| 13 | Reject or split any chunk over the embedding limit | 2026-10-30 |
| 14 | Unload the LLM after ingestion jobs; test `gemma4:e4b` alone in Stage 3 before relying on it | 2026-10-30 |
| 15 | Chunks store `locator_start` and `locator_end`, read according to the document's `locator_kind` | 2026-10-30 |
| 16 | Baseline top-5 uses the 4,000-token evidence maximum; the 2,500 target applies from Stage 5 | 2026-10-30 |
| 17 | Ollama embedding calls use `truncate=False`, so over-limit input is an error | 2026-10-30 |
| 18 | PDF loader handles two-column pages, rotated stamps, and line-break hyphens, after real-PDF testing | 2026-10-30 |
| 19 | Benchmark documents approved: 3 dev and 5 test, listed in `benchmarks/manifest.yaml` | 2026-10-30 |
| 20 | Score floors: 0.25 for `embeddinggemma:300m`, 0.47 for `bge-m3:latest`, set in `config.py`. Chosen inside the score gap, not by the `calibrate` rule, which sits on the edge of the answerable scores | 2026-11-02 |
| 21 | Stop testing `deepseek-r1:8b` as judge: about 4x slower than `gemma4:e4b` on the same probes on this Mac; error-catching not measured | 2026-11-02 |
| 22 | Judge: `gemma4:e4b` with the audit prompt and code check, plus the gold comparison | 2026-11-02 |
| 23 | Keep `embeddinggemma:300m`. Retest `bge-m3:latest` in Stage 4, specifically on table questions | 2026-11-02 |
| 24 | Recall@budget uses 2560 tokens, not 2000. Old and new numbers are not comparable | 2026-11-02 |
| 25 | Gold evidence supports "any of these" through `alternatives` on each evidence item | 2026-11-02 |
| 26 | Gold evidence pages are physical PDF pages | 2026-11-02 |

## Smoke test results (2026-10-30)

**Setup:** MacBook Air M4, 16 GB. Ollama 0.40.8, Python 3.11.18, `num_ctx` 8192. Five hand-written passages of about 170 words each, no real PDFs. VS Code, Chrome, Claude, and Spotify were open. This is a feasibility check, not a benchmark.

| Measure | Result |
|---|---|
| Question generation, `think=False` (10 questions) | Median 5.6 s, max 6.5 s warm; 10.1 s first, including load. 10/10 valid JSON, 10/10 quotes found |
| Question generation, thinking on (5 questions) | About 75 s each; 0/5 usable, all hit the 1024-token limit |
| Answer, ~2,600 prompt tokens (warm) | 19–22 s, about 18 tokens/s |
| Answer, ~3,900 prompt tokens (warm) | About 33 s, about 17 tokens/s |
| Answer, ~6,050 prompt tokens (warm) | 59–68 s, 10–13 tokens/s |
| Prompt reading speed | About 110–165 tokens/s |
| Embeddings, batches of 32 | 29.2 chunks/s at ~236 tokens; 16.1 at ~462; 8.0 at ~917 |
| Embedding a query | 13 ms warm; 1.1 s cold |
| Over-limit embedding input | 3,000 words accepted silently; 2,048 tokens processed |
| Model size reported by Ollama | LLM 5.8 GB + embeddings 0.7 GB = 6.5 GB, 100% GPU |
| Peak system memory in use | 15.4 of 17.2 GB (active + wired + compressed) |
| Lowest macOS free-memory level | 13% |
| Swap | 0 to about 5.1 GB; still 4.0 GB after unloading |

**Caveats:**
- Test answers were short (50–128 tokens), so longer answers will take more time.
- Generated passages were short (about 280 prompt tokens), so longer ones will take more time.
- Question quality was only lightly checked. Median word overlap with the quote was 0.24, and some questions are long and multi-part.
- The slowdown at 6,000 tokens may come from memory pressure or heat. The cause was not established.
- 40 questions is about 3.7 minutes per document, estimated from the median.
- `gemma4:e4b` was not tested. It is listed at 9.6 GB.

## Stage 2 results

**Built:** config, SQLite schema and migrations, PDF/DOCX/TXT loaders with validation, fixed 512/50 chunker, Ollama providers, Chroma wrapper, ingestion with versioning and crash repair, baseline top-5 retrieval, grounded answers with server-built citations, and the FastAPI API. Run it with `python -m adaptive_rag`.

**Tests (2026-10-30):**
- Unit and integration tests with fake providers: 121 passed. Run with `pytest`.
- Real Ollama tests: 6 passed, 1 expected failure. Run with `pytest -m ollama`.
- `ruff check` and `ruff format --check` are clean.

**Real-document check.** This was manual, with 8 questions. It is not a benchmark, and no retrieval metrics exist yet.

| Measure | Result |
|---|---|
| Documents | arXiv 2410.13070 (21 pages, two-column); NIST AI 100-1 (48 pages). Neither is stored in the repo |
| Ingest time | 3.2 s (28 chunks); 5.4 s (45 chunks) |
| Answer time, about 3,000 prompt tokens | 24–30 s |
| Refusals | 3 of 3 out-of-scope questions; 2 by the score gate, 1 by the LLM |
| Top scores | Out-of-scope 0.07–0.21; answerable 0.62–0.73 |

The rotated-text filter and idle-unload check were added after this run. Afterwards, the stamp was confirmed gone from extraction and the test suites were rerun, but these 8 questions were not repeated.

**Known limitations:**
- One answer was marked `answered` but missed the point. Asked about the sentence-level chunking limitation, the system cited other passages and not the paper's Limitations section. Stage 3 needs to measure how often this happens.
- The score floor of 0.2 is uncalibrated. One out-of-scope question scored 0.2138, passed the gate, and was refused only by the LLM.
- Prompt injection was tested on one example. The model didn't obey it and no citation was forged, but it tends to mention the injected claim while flagging it as untrusted. That is the expected failure in the real tests.
- Two-column detection has been tested on one real paper. Full-width tables are flattened, and some false headings occur, such as an author line.
- No OCR: scanned PDFs fail with a clear message. Pages with no text produce a warning.
- PDF citations use physical page numbers, not printed labels. A chunk can span pages, so a citation can be a range.
- Baseline evidence has no dedupe, so overlapping chunks repeat text.
- Unloading the LLM after ingestion adds model-load time to the next query.
- There is no endpoint to delete a knowledge base. Re-embedding isn't shared across knowledge bases.
- `tiktoken` needs internet once to download its encoding, then uses its cache.

## Stage 3 results so far (dev set only)

**Built:** PDF table-versus-column fix (`pdf-5`), span metrics, question generator with bias filters, bootstrap intervals, runner, report, calibration, comparison, and leakage check. Experiment scripts are in `benchmarks/analysis/`; their outputs are in `benchmarks/results/`.

**Tests (2026-11-02, after the decision changes):** 176 passed, 7 Ollama tests deselected and not rerun. `ruff check` and `ruff format --check` are clean.

**Question source:** 39 dev questions, LLM-generated and assistant-written, reviewed by the assistant and not by a human. The user checked the 7 wrong-focus labels against the PDFs and agreed with all of them (2026-11-02). The other 21 `answered` labels and all probe labels are the assistant's.

### Baseline: `embeddinggemma:300m`, fixed 512/50, top-5

Old setup, from `dev_embeddinggemma_300m_20261030T084407`: 2000-token budget, single-location gold, old judge prompt. **Not comparable with the rerun.** There is no report yet for the new setup.

| Metric | Result |
|---|---|
| Recall@budget (2000 tokens) | 0.655 (95% CI 0.483–0.828) |
| Hit rate@5 | 0.759 (95% CI 0.586–0.897) |
| MRR | 0.564 (95% CI 0.422–0.708) |
| Unanswerable refused, gate off | 10 of 10 |
| Generation p50 / p95 | 36.0 s / 59.7 s |

### Wrong-focus answers

The citation signal flagged 7 of 28 `answered` results. By hand, 3 of 28 are wrong and 4 are correct answers whose gold evidence was too narrow, because the fact also appears elsewhere.

| Case | Hand reading | Gold chunk rank |
|---|---|---|
| `tesla-a1` | Wrong: gave $832M, which is R&D stock compensation; the real figure is $4,540M | 6 |
| `tesla-a3` | Wrong: gave $49M, which is the VIE subset; the real figure is $16,139M | Not in top 30 |
| `nist_ai_rmf-gen-015` | Wrong: used a passage about risk tolerance | 16 |
| `tesla-a4`, `nist-a1`, `ragas-gen-000`, `ragas-gen-010` | Correct, from another passage | n/a |

**Cause, tested by changing one thing at a time** (`cause_experiment_20261102T054159.json`):

| Change | Answers fixed |
|---|---|
| Gold chunk placed in the evidence | 3 of 3 |
| Stricter prompt, same evidence | 0 of 3 |
| Misleading chunk given its table title | 0 of 2 |

Retrieval is the direct cause. Chunking is the likely reason for the retrieval miss: a hand-cut passage around the answer would have ranked first in all 3 cases. That is an upper-bound check, since only that one passage was re-scored and nothing was rechunked. Stage 4 has to measure it properly. `qwen3.5:9b` also takes a wrong table figure even when the title is visible, so the LLM is a weak last line of defence.

### Judge

Faithfulness of 1.000 has two separate causes:
1. Faithfulness can't see these failures. Two of the three wrong answers repeat a figure that really is in the evidence.
2. `gemma4:e4b` with the current prompt does miss errors, but it isn't blind.

Hand-labelled probes (`judge_experiment_20261102T054202.json`):

| `gemma4:e4b` configuration | Planted unsupported claims caught | Off-topic caught | Real failures caught | False alarms on clean |
|---|---|---|---|---|
| v1, current prompt | 11 of 14 | 5 of 6 | 0 of 3 | 0 of 11 |
| v2, audit prompt | 12 of 14 | 6 of 6 | 0 of 3 | 0 of 11 |
| v2 plus code check of quotes and numbers | 13 of 14 | 6 of 6 | 0 of 3 | 0 of 11 |
| v3, compare to gold reference, on 28 real answers | n/a | n/a | 2 of 3 | 0 of 25 |

Caveats:
- The probes are small and were written by the assistant, who also wrote the prompts while knowing the failure types. The v2 and v3 scores may be optimistic.
- The code check's date handling was corrected after seeing a false alarm, and the scores were recomputed from saved output.
- v2 has not been run on the 25 real correct answers, so its real false-alarm rate is unknown.
- The v2 prompt says about one answer in two has errors, which isn't true of real answers.

`deepseek-r1:8b`: stopped by the user's decision after 8 of 96 planned calls, all on clean probes with the current prompt. It averaged 71 s against 18 s for `gemma4:e4b` on those same 8 probes, about 4x. An earlier "about 7x" compared different sets of probes and was wrong; the 18 s also includes `gemma4:e4b`'s first-call model load. 7 of 8 outputs were valid and raised no false flags; 1 hit the 800-token limit with no usable output. Its ability to catch errors was not measured, because no planted-error probe was reached.

The table's v1 to v3 scores come from the experiment script. The adopted judge in `evaluation/judge.py` uses the same prompts and the corrected code check, but has not yet run through the real pipeline.

### Score floor

| Top-score range | `embeddinggemma:300m` | `bge-m3:latest` |
|---|---|---|
| Out-of-scope, benchmark (3) | 0.073–0.108 | 0.349–0.384 |
| Out-of-scope, extra probes (15) | 0.056–0.151 | 0.314–0.424 |
| Terse answerable probes (15) | 0.322–0.727 | 0.510–0.724 |
| Answerable, benchmark (29) | 0.445 and up | 0.568 and up |
| Near-miss, benchmark (7) | 0.455–0.602 | 0.520–0.663 |
| **Floor set** | **0.25** | **0.47** |

Both floors block 0 of 29 answerable, 0 of 15 terse, and pass 0 of 18 out-of-scope questions. No floor can separate near-miss from answerable questions: the rank separation (AUC) is 0.61 for `embeddinggemma:300m` and 0.75 for `bge-m3:latest`. Near-misses depend entirely on the LLM's refusal, which was 10 of 10 on `embeddinggemma:300m` evidence and is untested on `bge-m3:latest`. The `calibrate` rule picked 0.44, which would block 2 of the 15 terse probes. In retrieval-only runs, its `false_answers` and `system_refused` columns are meaningless because no LLM ran.

### Embedding comparison (29 answerable, retrieval only)

Old setup with a 2000-token budget. Not rerun, because the retest is planned for Stage 4. The "gold widened" column was a one-off sensitivity check. The score floors above don't depend on the budget or the gold evidence.

| Metric, `bge-m3:latest` minus `embeddinggemma:300m` | As labelled | Gold widened for narrow cases |
|---|---|---|
| Recall@budget | +0.133 (−0.009 to +0.306), tie | +0.030 (−0.078 to +0.159), tie |
| Hit rate@5 | +0.069 (−0.069 to +0.207), tie | 0.000 (−0.103 to +0.103), tie |
| MRR | +0.094 (+0.033 to +0.163), different | +0.051 (−0.019 to +0.122), tie |

Table questions had a hit rate@5 of 0.8 for `bge-m3:latest` and 0.4 for `embeddinggemma:300m`, on only 5 questions. Indexing took about 69 s against 38 s, measured on separate days and not as a controlled benchmark. Vectors have 1024 dimensions against 768; models are 1.2 GB against 621 MB. `bge-m3:latest` has no answer or judge run.

### Implemented, not yet measured in a report

- **Recall@budget is now 2560 tokens** (`RECALL_BUDGET_TOKENS` in `runner.py`). At 2000, only 3 chunks of 512 and 1 of 1024 fit. `compare` refuses runs with different budgets. The two old reports carry a "not comparable" note.
- **`alternatives` on evidence** in `benchmark.py`, `metrics.py`, `runner.py`, and `validate`. `questions_dev.yaml` has them on `tesla-a1`, `tesla-a4`, `nist-a1`, `ragas-gen-000`, and `ragas-gen-010`. All `page: null` entries are filled, and the file passes `validate`.
- **Judge** in `judge.py`: audit prompt, code check of quotes and numbers, and `compare_to_reference`. The report has a new row for the gold comparison.
- **Template:** `benchmarks/questions_template.yaml`, which passes `validate`.

### Known issues

- The audit prompt tells the judge about one answer in two has errors, which isn't true of real answers. It was kept as measured. The false-alarm check will show whether that matters.
- In retrieval-only runs, the `false_answers` and `system_refused` columns from `calibrate` are meaningless.
- `data/eval/dev_bge-m3/` is an empty leftover from the earlier failed attempt. The real index is `data/eval/dev_bge-m3_latest/`. Both are gitignored.
- The stopped rerun added extra rows to `query_traces` in `data/eval/dev_embeddinggemma_300m/`. They are harmless and gitignored.

## Workspace state

- Git is initialized with `.gitignore`. Stage 2 is committed on `main`; Stage 3 so far is a WIP checkpoint on branch `stage-3-evaluation-harness`, not merged. Commit only when the user asks.
- The conda env `adaptive-rag` exists (Python 3.11.18) with the project installed in editable mode.
- Ollama 0.40.13. Models installed: `embeddinggemma:300m`, `bge-m3:latest`, `qwen3.5:9b`, `gemma4:e4b` (same digest as `gemma4:latest`), `deepseek-r1:8b`. `qwen3.5:4b` (the fallback) is not installed.
- The test documents have not been read, indexed, or run. They are in `benchmarks/documents/test/`, gitignored. `questions_test.yaml` didn't exist at last check; the user is writing it. Don't read the test documents or the user's questions; `validate` prints IDs and errors only.
- No evaluation process is running, and no models are loaded in Ollama.

## Next steps (Stage 3)

Run from the repo root with `conda activate adaptive-rag`. Don't run the two LLM jobs at the same time.

1. **Rerun the dev report.** The last attempt was stopped by the user on 2026-11-02 at the 21st question or later. Results are saved only at the end, so nothing was kept. The 2026-10-30 run took about an hour; the audit judge takes longer per call. Use a background job:
   ```
   python -m adaptive_rag.evaluation run --set dev --questions benchmarks/questions_dev.yaml --judge --question-source "39 dev questions; LLM and assistant-written; assistant-reviewed, not human" --notes "Recall@budget uses 2560 tokens and gold evidence allows alternatives, so it is not comparable with earlier reports. Judge: audit prompt with code check, plus gold comparison."
   ```
2. **Measure the audit judge's false alarms.** This uses the saved answers from the 2026-10-30 run: 25 labelled correct (4 confirmed by the user, 21 the assistant's reading) and 3 wrong (user-confirmed). A false alarm is `llm_flag`, `code_flag`, or `off_topic_flag` on a correct answer. Report all of it, including any poor result.
   ```
   python benchmarks/analysis/audit_false_alarms.py
   ```
3. **Update the docs.** Record both results here. In `DESIGN.md`, change the 2000-token Recall@budget (section 5), the judge row (section 3), and the evidence description, and add the `bge-m3:latest` table retest to the Stage 4 tasks. None of these `DESIGN.md` changes are done yet.
4. **Ask the user before committing the results.** The WIP checkpoint was made before the rerun. Before any commit, confirm that no files under `data/`, no `.env`, and no benchmark PDFs are staged.
5. **Wait for the user's `questions_test.yaml`,** then run `validate` on it. The user may add `alternatives` wherever a fact appears in several places.
6. **Close Stage 3** with the end-of-stage report, including a reported wrong-focus rate from the new run. Stop and wait for approval before Stage 4.

## Open questions

- None waiting on the user right now, other than the commit confirmation and `questions_test.yaml`.
