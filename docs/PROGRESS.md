# Adaptive RAG: Progress

**Last updated:** 2026-11-04
**Current state:** Stage 5 on branch `stage-5-adaptive-retrieval` (uncommitted). Adaptive retrieval is built and tested; the dev retrieval-only sweep is done. **At equal budget, S ≈ A on dev.** Waiting for the user's decision on next steps (hybrid keyword search, budget) before any answer run.

The approved architecture is in [DESIGN.md](DESIGN.md).

## Stage status

| Stage | Name | Status |
|---|---|---|
| 1 | Design | Complete; approved 2026-10-30 |
| 2 | Baseline backend | Complete and committed 2026-10-30 |
| 3 | Evaluation harness | Complete; approved 2026-11-04 |
| 4 | Chunking optimization | Complete; approved 2026-11-04 |
| 5 | Adaptive retrieval | In progress: built, dev sweep done; waiting for the user's decision |
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
| 27 | Evaluation runs save after every question and judge call, and resume with `--resume <results file>` | 2026-11-03 |
| 28 | Adopt the looser code check (`judge_check` `loose-1`). It was tuned on the dev answers, so its false-alarm rate must be confirmed on the test set before it is reported | 2026-11-03 |
| 29 | Faithfulness doesn't catch wrong-table answers. Use the citation check (citation off gold evidence) and the gold comparison to detect wrong answers, not faithfulness | 2026-11-03 |
| 30 | Test questions: 30 written by Claude in a separate chat session, not by the user or this assistant; the user spot-checked 5 against the PDFs. This departs from the design's human-written test set | 2026-11-04 |
| 31 | User labels for 8 test answers: `bp-03` and `fed-02` wrong; the other 6 correct. Gold for `fed-01` and `apple-06` was too narrow. The test file was left unedited and the test set was not rerun | 2026-11-04 |
| 32 | Defer the human-written test subset to Stage 8 | 2026-11-04 |
| 33 | Stage 4 adds a 7th chunking candidate, C7 table-aware recursive (up to 512 tokens), measured separately from structure-aware C5 | 2026-11-04 |
| 34 | About 15 new dev table questions, written by Claude in a separate chat session and spot-checked by the user. Record `source` that way. They must be in before any candidate is scored | 2026-11-04 |
| 35 | Add the Federal Reserve Monetary Policy Report, February 2025, as a 4th dev document (`dev/fed_mpr_feb2025.pdf`; public domain, cite the Board; SHA-256 checked). The Fed report on test (June 2025) is not opened or analysed before the final run | 2026-11-04 |
| 36 | `bge-m3:latest` switching rule, fixed before the run: switch only if it is better on dev table questions with a 95% CI that excludes zero, and not clearly worse overall (CI of the overall difference not entirely below zero). Otherwise keep `embeddinggemma:300m` | 2026-11-04 |
| 37 | Quote location prefers a match that starts on the stated page, else the first match. Needed because the same table row can appear on several pages. It moved 0 of 34 dev and 0 of 37 test gold quotes, so earlier results stand | 2026-11-04 |
| 38 | When extraction scrambles a gold row, shorten the quote to the part that survives intact, keep the question and answer unchanged, and record it as a known extraction failure in `notes`. Applied to `tbl-nist-01` and `tbl-nist-04` | 2026-11-04 |
| 39 | Table extraction stays unchanged in Stage 4, so B vs C measures chunking only. The flattened Fed Table 1 header is a known limitation | 2026-11-04 |
| 40 | Keep `embeddinggemma:300m`. The Stage 4 retest found 0 of 3 configs favouring `bge-m3:latest` | 2026-11-04 |
| 41 | C7's detector was tuned on dev, so any B or C dev score that uses C7 is reported as optimistic. The held-out test run is the only evidence for C7 | 2026-11-04 |
| 42 | Held-out comparison pre-registered: A (C1) vs C7 as a fixed config vs C (optimizer), all on `embeddinggemma:300m`. Primary: C7 minus A on Recall@budget, on test table questions and overall, with the paired CI rule. Replaces B vs C, since on dev A = B = C = C1 | 2026-11-04 |
| 43 | The optimizer's weaknesses are recorded as Stage 4 findings (about 10 min per document, 14–26 accepted questions, 0–1 table questions, saturated scores on small sampled pools). No further optimizer tuning in Stage 4 | 2026-11-04 |
| 44 | User's decision: product default chunking is C1. The optimizer (`chunking = "adaptive"`) and C7 are opt-in settings; code and tests kept. Findings recorded as: C7 vs A inconclusive; the optimizer chose C1 for all 9 documents at about 10 min each; remaining errors are table reading and multi-part retrieval depth. Stage 4 approved | 2026-11-04 |
| 45 | Stage 5 plan approved. Lean: retrieval-only sweeps first, answer runs only for finalists, features that don't help on dev stay off. Tune on dev only. Base chunking C1; evidence target 2,500 (equal to A's ~2,560), plus one dev check at 4,000 | 2026-11-04 |
| 46 | Rule-based per-part retrieval is in v1 (DESIGN.md section 6). About 12 new dev multi-part questions with 2–3 required evidence parts each, written by Claude in a separate session from `data/dev_multipart_prompt.txt` and spot-checked by the user, into `benchmarks/questions_dev_multipart.yaml` | 2026-11-04 |
| 47 | Table-reading prompt is a Stage 5 switch, measured on dev table questions. Table extraction changes are their own later stage (Stage 5b), not Stage 5 | 2026-11-04 |
| 48 | Held-out: A vs S (adaptive). A reuses Stage 4's `test_embeddinggemma_300m_C1_20261104T064322.json`, backed by a regression test that A's retrieval is unchanged. `fed-02`, `fed-04` and `bp-03` are reported separately as "seen", since they shaped the Stage 5 focus. Pre-registered and frozen by commit before the run | 2026-11-04 |
| 49 | Stage 5 dev selection rule, fixed before the first sweep: score = mean recall over the evidence actually sent, on all 56 answerable dev questions (29 dev, 15 dev table, 12 dev multi-part), paired with A by bootstrap. Start from the best config; a feature stays on only if switching it off lowers dev recall sent or multi-part part coverage; ties go to the simpler setting. Script: `benchmarks/analysis/stage5_sweep.py` | 2026-11-04 |

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

Old setup, from `dev_embeddinggemma_300m_20261030T084407`: 2000-token budget, single-location gold, old judge prompt. **Not comparable with the rerun below.**

| Metric | Result |
|---|---|
| Recall@budget (2000 tokens) | 0.655 (95% CI 0.483–0.828) |
| Hit rate@5 | 0.759 (95% CI 0.586–0.897) |
| MRR | 0.564 (95% CI 0.422–0.708) |
| Unanswerable refused, gate off | 10 of 10 |
| Generation p50 / p95 | 36.0 s / 59.7 s |

### Rerun with the new setup (2026-11-03)

`dev_embeddinggemma_300m_20261103T062301`: 2560-token budget, gold evidence with alternatives, audit judge with code check, plus gold comparison. It ran before resumable runs existed. The answers matched the 2026-10-30 run word for word on all 39 questions, so the generation is deterministic.

| Metric | Result |
|---|---|
| Recall@budget (2560 tokens) | 0.862 (95% CI 0.724–0.966) |
| Hit rate@5 | 0.862 (95% CI 0.724–0.966) |
| MRR | 0.661 (95% CI 0.521–0.793) |
| Wrong focus, citation off gold | 3 of 28: exactly the 3 user-confirmed wrong answers |
| Gold comparison: conflicts / different point | 2 / 0 of 28: `tesla-a1` and `tesla-a3`; it missed `nist_ai_rmf-gen-015` |
| Faithfulness (LLM judge) | 0.915 (95% CI 0.849–0.970) |
| Unanswerable refused, gate off | 10 of 10 |
| Generation p50 / p95 | 37.5 s / 48.8 s |

Recall@budget now equals recall@5, because 2560 tokens fits all 5 chunks of 512.

**Faithfulness of 0.915 is mostly judge noise, not answer errors.** All 3 wrong answers scored 1.0. The drop below 1.0 comes from correct answers flagged by the judge (next section).

### Audit judge false alarms (2026-11-03)

`audit_false_alarms_20261103T064126.json`. The judge was run on the saved 2026-10-30 answers: 25 correct and 3 wrong. 4 of the correct labels and all 3 wrong ones are user-confirmed; the other 21 are the assistant's.

| Signal | Correct answers flagged (false alarms) | Wrong answers flagged |
|---|---|---|
| LLM says unsupported | 2 of 25 | 0 of 3 |
| Code check fails | 5 of 25 | 0 of 3 |
| Off topic | 0 of 25 | 0 of 3 |
| Any | **7 of 25 (28%)** | **0 of 3** |

Causes:
- **Code check (5):** in 4 answers, the judge's quote wasn't exactly in the evidence. It had elided text with `[...]`, or garbled PDF formula text. In 1 answer, the "4" in "GPT-4" was treated as a figure missing from the quote. All 5 claims are true.
- **LLM (2):** `nist_ai_rmf-gen-004` makes an inference the evidence doesn't state, so that flag is arguably correct at claim level. `ragas-gen-000`'s judge picked the wrong sentence as its quote, so that one is a false alarm.

**Looser code check, tested offline** on the saved outputs, with no new LLM calls:
- **Rule:** split the quote at `[...]`; each piece must be found in the evidence, or 90% of its words must appear there; the claim's figures must appear anywhere in the evidence.
- **Result:** false alarms drop from 7 to 2 of 25. Planted errors caught drop from 13 to 12 of 14; the one lost is a wrong figure (3 instead of 1) that appears elsewhere in the same table. Real failures caught stay at 0 of 3.
- **Caveat:** this rule was designed after seeing these 25 answers, so it is fitted to them.
- **Adopted 2026-11-03** as `judge_check` `loose-1` in `judge.py`. The production code reproduces the offline counts: 2 of 25 correct answers flagged, 0 of 3 wrong, 12 of 14 planted errors caught, 0 of 11 clean probes flagged. **Its false-alarm rate is tuned on dev and must be confirmed on the test set before it is reported.** The 2026-11-03 report's faithfulness of 0.915 used the strict check. The next judge run will use the looser one.

**Faithfulness doesn't catch wrong-table answers.** The real failures are faithful to the wrong passage, such as a figure from a stock-compensation or VIE table, so every claim is "supported". Use the citation check and the gold comparison as the signals for wrong answers. The gold comparison catches 2 of 3. The wrong-focus signal from citations off gold catches 3 of 3 now that gold has alternatives.

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

### Held-out test run (2026-11-04, run once)

`test_embeddinggemma_300m_20261104T030739`, with the same setup as the dev rerun: audit judge, `loose-1` code check, gold comparison, and a 2560-token budget.

**Question source:** 30 questions (24 answerable: 6 table, 8 factual, 6 conceptual, 4 multi-part; 6 unanswerable: 4 near-miss, 2 out-of-scope) across the 5 test documents.
- **Who wrote them:** Claude, in a separate chat session, not the user and not this assistant. The user spot-checked 5 against the PDFs.
- **Evidence fields:** all 24 answerable questions have `expected_answer`, and 5 use `alternatives`.
- **How they were handled:** validated with an IDs-and-errors-only script; no problems. This assistant did not read the question text.

| Metric | Test | Dev rerun, for reference only |
|---|---|---|
| Recall@budget (2560 tokens) | 0.860 (95% CI 0.708–0.985) | 0.862 (0.724–0.966) |
| Hit rate@5 | 0.875 (0.750–1.000) | 0.862 (0.724–0.966) |
| MRR | 0.716 (0.572–0.850) | 0.661 (0.521–0.793) |
| Answerable: answered / partial | 23 / 1 | 28 / 1 |
| Citation off gold evidence | 3 of 23 | 3 of 28 |
| Gold comparison: conflicts | 2 of 23 | 2 of 28 |
| Faithfulness (judge, `loose-1`) | 0.882 (0.771–0.965) | 0.915 with the strict check, so not comparable |
| Unanswerable refused, gate off | 6 of 6 | 10 of 10 |
| Generation p50 / p95 | 33.7 s / 40.3 s | 37.5 s / 48.8 s |

These are different questions on different documents. The columns are not a paired comparison.

- **By document,** Recall@budget is 1.0 for the Apple 10-K, RAPTOR, and best-practices papers; 0.80 for NIST CSF; and 0.53 for the Fed report, the weakest.
- **By type,** hit@5 is 5 of 6 for table questions, 6 of 8 factual, 6 of 6 conceptual, and 4 of 4 multi-part.
- **Score floor 0.25, replayed on test:** it blocks 0 of 24 answerable questions (lowest top score 0.416) and both out-of-scope ones (0.109 and 0.133). It doesn't stop near-misses (0.56–0.65), as on dev; the LLM refused all 4. This confirms the dev calibration on held-out data.

**Wrong answers, with the user's labels (2026-11-04).** The user checked 8 answer IDs against the PDFs. The other 16 answered or partial results are unlabelled. They are counted as correct below because the citation check and gold comparison both pass them, but no human checked them.

- **Wrong: 2 of 24** answerable. `bp-03` (`answered`) took the 1024-token setting's score (94.26) instead of the right one (97.59). `fed-02` (`partial`) gave the 2027 value (2.1%) instead of the March value in the same table. Both are wrong-cell answers from the right table: the right passage was retrieved, and the wrong figure was read from it.
- **Correct:** `apple-03`, `fed-01`, `csf-01`, `fed-05`, `raptor-03`, and `apple-06`.
- **Gold too narrow:** `fed-01`, and `apple-06`, where the equity statement on p. 35 shows 95,846. Per the user, `questions_test.yaml` was not edited and the test set was not rerun, so the report's figures stand as computed with the narrow gold.

How each signal did on the 22 correct and 2 wrong answers:

| Signal | Correct answers flagged (false alarms) | Wrong answers caught |
|---|---|---|
| Judge: unsupported claim or off topic (`audit-1` + `loose-1`) | **3 of 22 (14%)**: `apple-06`, `fed-05`, `raptor-03` | 2 of 2 |
| Citation off gold evidence | 3 of 22: `apple-03`, `fed-01`, `csf-01` | 1 of 2 (`fed-02`) |
| Gold comparison: conflicts | 1 of 22: `apple-06`, narrow gold | 2 of 2 |

- **Measured false-alarm rate of the looser code check on test: 3 of 22 (14%),** for the judge's combined flag. 16 of the 22 "correct" answers rest on the two signals passing rather than on human labels. Dev was 2 of 25 (8%). With samples this small, the difference is not meaningful. This replaces the 2-of-18 proxy.
- **Signals compared across sets:** the gold comparison was the most reliable on both. On test, it caught 2 of 2 wrong answers with 1 false alarm, caused by narrow gold; on dev, it caught 2 of 3 with 0 false alarms. The citation check was strong on dev (3 of 3, no false alarms) but weak on test (1 of 2, 3 false alarms), because both test errors cited the right table and read the wrong cell. The judge caught both test errors but none of the 3 on dev.
- **Practical reading:** use the gold comparison as the main wrong-answer signal, with the citation check and judge as supporting signals. None of them works on live queries, where there is no gold. Decision 29 stands; this result refines it.

### Implemented

- **Recall@budget is now 2560 tokens** (`RECALL_BUDGET_TOKENS` in `runner.py`). At 2000, only 3 chunks of 512 and 1 of 1024 fit. `compare` refuses runs with different budgets. The two old reports carry a "not comparable" note.
- **`alternatives` on evidence** in `benchmark.py`, `metrics.py`, `runner.py`, and `validate`. `questions_dev.yaml` has them on `tesla-a1`, `tesla-a4`, `nist-a1`, `ragas-gen-000`, and `ragas-gen-010`. All `page: null` entries are filled, and the file passes `validate`.
- **Judge** in `judge.py`: audit prompt, code check of quotes and numbers, and `compare_to_reference`. The report has a new row for the gold comparison.
- **Template:** `benchmarks/questions_template.yaml`, which passes `validate`.
- **Resumable runs** (2026-11-03): `runner.py` saves after every question and judge call, writing via a temporary file. `run --resume <file>` skips answered questions and judged ones. It refuses if the questions file, models, judge prompt, budget, or retrieval-only mode differ from the saved run. `calibrate` and `compare` refuse incomplete files. Tests: 180 passed. Also checked through the CLI by cutting a retrieval-only run back to 17 of 39 questions and resuming it; the result matched an uninterrupted run exactly.

### Known issues

- The audit prompt tells the judge about one answer in two has errors, which isn't true of real answers. It was kept as measured. On real answers, only 2 of 7 false alarms came from the LLM, so it doesn't look like the main problem. That wasn't tested directly.
- In retrieval-only runs, the `false_answers` and `system_refused` columns from `calibrate` are meaningless.
- `data/eval/dev_bge-m3/` is an empty leftover from the earlier failed attempt. The real index is `data/eval/dev_bge-m3_latest/`. Both are gitignored.
- The stopped rerun added extra rows to `query_traces` in `data/eval/dev_embeddinggemma_300m/`. They are harmless and gitignored.

## Stage 4 progress

### Step 1: 4th dev document (2026-11-04)

- **Source:** linked from the Fed's MPR page; the URL is `/publications/files/20250207_mprfullreport.pdf`, not the `/monetarypolicy/files/` path the June edition uses. PDF metadata title: "Monetary Policy Report, February 2025", 83 pages.
- **Licence:** the Board's site says its information is public domain unless marked otherwise, and asks for the Board to be cited.
- **`download`:** all 9 manifest hashes are ok. Leakage tests pass (2 passed).
- **Extraction with the current PDF loader:** about 44k tokens, 100 sections. One warning: no text on pages 2, 4 and 82.

Rough dev-document profile. `numeric lines` is a crude count of lines that are at least half figures, a one-off check and not the C7 table detector:

| Document | Pages with text | Tokens | Numeric lines | Extract time |
|---|---|---|---|---|
| Tesla 10-K | 142 | 100,400 | 363 (7%) | 13.1 s |
| NIST AI RMF | 47 | 20,442 | 11 (1%); Tables 1–4 are text tables that continue across pages | 1.7 s |
| Ragas | 8 | 7,922 | 3; one small table with its caption below it | 0.4 s |
| Fed MPR, Feb 2025 | 80 | 44,211 | 131 (4%); Tables 1 and 2 | 4.1 s |

**Finding, dev only:** in the Fed's Table 1 (economic projections), extraction flattens the header. "Longer run" becomes the lines `Longer Longer Longer` and `Variable run run run`, so each row is 15 numbers whose columns can't be read reliably from the text. Chunking can keep the header with the rows, but it can't make the columns readable. This is an extraction problem.

### Step 2: dev table questions (2026-11-04)

`benchmarks/questions_dev_tables.yaml`: 15 table questions (6 Fed, 4 Tesla, 4 NIST, 1 Ragas), written by Claude in a separate chat session. The user spot-checked `tbl-fed-03`, `tbl-fed-06`, `tbl-tsla-02` and `tbl-ragas-01` against the PDFs and found them correct. With the 5 existing Tesla table questions, dev now has 20 table questions.

- **First `validate`:** all 6 Fed quotes matched, including footnote markers.
  - `tbl-tsla-01`: the same row appears on pages 40, 52 and 58, and matching always took the first, so the stated page and its alternatives were reported wrong. This was a harness bug, fixed by decision 37.
  - `tbl-nist-01` and `tbl-nist-04`: not found. The loader interleaves these rows line by line with the table's left column, so the sentence is never contiguous. Handled by decision 38.
- **After the fixes:** all 15 quotes are found on their stated pages. `questions_dev.yaml` and `questions_test.yaml` still validate.
- **Overlap with test questions** (`benchmarks/analysis/question_overlap.py`, results in `question_overlap_20261104T051951.json`). It prints IDs and scores only. Thresholds fixed before the run: question Jaccard ≥ 0.5, cosine ≥ 0.85 (`embeddinggemma:300m`), or an identical quote. **0 of 15 flagged.** The closest pair is `tbl-fed-05` and test `fed-02`, with cosine 0.779 and Jaccard 0.294, as expected for two editions of the same report.

### Step 3: chunkers (2026-11-04)

Built:
- `chunking/recursive.py` (C2–C4): splits at paragraphs, then lines, sentences, words and tokens, then merges greedily up to the size. Overlap is the last ≤N tokens of the previous chunk, starting at a sentence boundary if there is one, else at a word boundary. The first version repeated only whole pieces, so on paragraph-sized pieces it gave no overlap at all; a test caught this.
- `chunking/tables.py`: a table detector based on line rules. A row is a line that ends in 2 or more figures. A table needs at least 3 rows with a text label, so chart axis ticks don't count. Its title is up to 6 lines above, stopping at a blank line, a sentence end or a "Table N" line. A caption directly below is included.
- `chunking/table_aware.py` (C7): a table that fits is one chunk. A larger table is split only at line ends, and each continuation chunk carries the header as a second character range (`context_start`/`context_end`, at most 150 tokens). That range is counted inside the chunk size.

**Tests:** 24 new, in `tests/test_chunking_stage4.py`. They cover offsets, sizes, coverage, multibyte text, paragraph preference, overlap bounds, token fallback, settings, table rules (chart ticks, prose with numbers, captions, header cap), C7 row-only splits with header context, and C7 equalling recursive when there are no tables. Full suite: 210 passed, 7 Ollama tests deselected. `ruff` is clean.

**Structural check on the dev documents.** This is not a retrieval score.

| Document | Tables found | Table share of tokens | C7 chunks (table / with context) | C3 chunks |
|---|---|---|---|---|
| Tesla 10-K | 51 | 10.7% | 281 (55 / 4) | 224 |
| NIST AI RMF | 0 | 0% | 49 | 49 |
| Ragas | 1 | 1.0% | 19 (1 / 0) | 17 |
| Fed MPR, Feb 2025 | 5 | 3.7% | 105 (7 / 2) | 100 |

- The gold row of all 20 dev table questions lies inside one C7 chunk. For the 16 in numeric tables, that chunk is a table chunk; Tesla R&D (`tesla-a1`) now sits in a 93-token chunk with its title.
- **Fed tuning (dev):** the detector first found 22 Fed "tables", about 15 of them chart axis labels. The labelled-row rule cut this to 5: Tables 1 and 2, Table A in two parts, and one false positive where a chart legend runs into prose. The rule was chosen by reasoning about what a table row looks like, then checked on this dev document.
- **Fed Table 1** (about 1,050 tokens) is split into 3 chunks. Pieces 2 and 3 carry the header, starting at "Table 1.". The header itself is still flattened (decision 39).

**Not done yet:**
- The DB schema doesn't store `context_start`, `context_end` or `is_table`.
- Ingestion and retrieval don't use C7 or `embedding_text`.
- The evidence budget doesn't yet count context tokens.
- C5 structure-aware and C6 semantic aren't built.
- Nothing has been scored.

**Known limitations:**
- Text-only tables, such as NIST's category tables, aren't detected, so C7 treats them as prose. Their rows are also scrambled by extraction.
- A row's label line can end up at the end of the previous piece, as with Fed "Memo: Projected appropriate policy path".

### Step 3b: checkpoint, context budget, C5, C6, profiler, optimizer (2026-11-04)

- **Checkpoint commit:** `010f056` on `stage-4-chunking-optimization`. Checked: no `data/`, `.env`, PDFs or DB files.
- **C7 context is charged everywhere:**
  - `Chunk.evidence_tokens` and `RetrievedChunk.evidence_tokens` are text tokens plus context tokens.
  - `fit_to_budget` (the LLM evidence), the runner's Recall@budget input, and the optimizer's in-memory scoring all use `evidence_tokens`.
  - The LLM evidence block shows the context before the chunk.
  - Migration `002_chunk_context.sql` adds `context_start`, `context_end`, `context_text`, `context_tokens` and `is_table` to `chunks`. Ingestion stores them and embeds `embedding_text`.
  - 6 tests in `tests/test_context_budget.py`.
- **C5** `chunking/structure.py` and **C6** `chunking/semantic.py`, with rules as in DESIGN.md section 5.
- **Optimizer** `src/adaptive_rag/optimizer/`:
  - `profile.py`: format, pages, tokens, heading density, section stats, table share, characters per page, language, reliable headings.
  - `candidates.py`: C1–C7 and the simplicity order.
  - `sampling.py`: regions and the question plan.
  - `scoring.py`: in-memory NumPy index.
  - `selection.py`: the design's rule.
  - `embcache.py`: disk cache keyed by model, digest, prompt version, title and text.
  - `optimize.py`: orchestration and caps.
- **Question generator:** `generate_for_plan` takes explicit windows, a `table` type, a maximum number of accepted questions, and a deadline. The Stage 3 `generate_questions` is unchanged in behaviour.
- **Two cap bugs found by tests and fixed:**
  - Snapping samples to line boundaries could blow the 30k-token cap on documents with very long lines (48k measured in a test).
  - The 3-table-question minimum couldn't be met with one table.
- **Tests:** 18 in `tests/test_optimizer.py`, covering C5 boundaries, C6 breakpoints and regions, profile, sampling caps, the table question plan, context charging, three selection cases, the question, call, time and candidate caps, LLM unload before embedding, the control fallback, and the cache. Full suite: 234 passed, 7 Ollama tests deselected. `ruff` is clean.
- **Not yet:**
  - The optimizer hasn't run on a real document, so no ingest cost is measured.
  - There is no registry or reuse logic.
  - Ingestion still always uses C1.

### Step 4: `bge-m3:latest` retest, procedure fixed before running (2026-11-04)

Written before any retest number existed.

- **Data:** the 4 dev documents in one pool, like one knowledge base. Questions: the 29 answerable questions in `questions_dev.yaml` plus the 15 in `questions_dev_tables.yaml`, 44 in all. Table questions: 20. **Clean table questions: 18**, without `tbl-nist-01` and `tbl-nist-04`, which are reported separately as known extraction failures.
- **Setup:** in-memory exact cosine search (`optimizer/scoring.py`), pool of 30, Recall@budget at 2560 tokens charged as evidence tokens (text plus C7 context), and the same metrics as Stage 3. The title in the embedding prompt is the file stem, as in ingestion.
- **Grid:** {`embeddinggemma:300m`, `bge-m3:latest`} × {C1 fixed 512/50, C3 recursive 512/50, C7 table-aware 512/50}.
- **Rule (decision 36), applied per chunking config:** that config favours `bge-m3:latest` if the paired 95% bootstrap CI of `bge-m3` minus `embeddinggemma` on Recall@budget over the 18 clean table questions lies entirely above zero, **and** the CI over all 44 questions isn't entirely below zero.
- **Decision:** switch only if at least 2 of the 3 configs favour `bge-m3`. Otherwise keep `embeddinggemma:300m`.
- **Not comparable with Stage 3:** this setup has a 4th document (more distractors), exact in-memory search instead of Chroma HNSW, and 15 more questions.

### Step 4 result (2026-11-04): keep `embeddinggemma:300m`

`benchmarks/results/embedding_retest_20261104T054418.json`, run on commit `010f056` with uncommitted Stage 4 changes. Digests: `embeddinggemma:300m` `85462619…`, `bge-m3:latest` `79076464…`.

**By the rule, 0 of 3 configs favour `bge-m3`.** On clean table questions, its CI never lies entirely above zero, and every point estimate is at or below `embeddinggemma`'s. **Decision by the fixed rule: keep `embeddinggemma:300m`.** The user confirmed it on 2026-11-04 (decision 40).

Recall@budget at 2560 tokens, mean (95% CI). Differences are `bge-m3` minus `embeddinggemma`, paired:

| Config | Subset | n | `embeddinggemma` | `bge-m3` | Difference |
|---|---|---|---|---|---|
| C1 fixed | All | 44 | 0.841 (0.727–0.932) | 0.747 (0.611–0.864) | −0.094 (−0.205 to 0.000) |
| C1 fixed | Clean table | 18 | 0.722 (0.500–0.889) | 0.556 (0.333–0.778) | −0.167 (−0.389 to +0.056) |
| C1 fixed | Non-table | 24 | 0.917 (0.792–1.000) | 0.869 (0.708–0.994) | −0.047 (−0.136 to 0.000) |
| C3 recursive | All | 44 | 0.886 (0.773–0.977) | 0.760 (0.633–0.873) | −0.127 (−0.273 to +0.023) |
| C3 recursive | Clean table | 18 | 0.778 (0.556–0.944) | 0.635 (0.413–0.833) | −0.143 (−0.421 to +0.111) |
| C3 recursive | Non-table | 24 | 0.958 (0.875–1.000) | 0.833 (0.667–0.958) | −0.125 (−0.292 to +0.042) |
| C7 table-aware | All | 44 | 0.955 (0.886–1.000) | 0.909 (0.818–0.977) | −0.045 (−0.159 to +0.068) |
| C7 table-aware | Clean table | 18 | 1.000 (1.000–1.000) | 1.000 (1.000–1.000) | 0.000 |
| C7 table-aware | Non-table | 24 | 0.917 (0.792–1.000) | 0.833 (0.667–0.958) | −0.083 (−0.292 to +0.125) |

- **Known extraction failures,** reported separately: `tbl-nist-01` and `tbl-nist-04` reach Recall@budget 1.0 under both models and all configs. Their quotes were shortened to the part that extraction keeps intact, so this is a weak test. The gold rank is 2–3 for `embeddinggemma` and 1–4 for `bge-m3`.
- **Stage 3's wrong-answer misses:**
  - `tesla-a3`: under C1 it is outside the top 30 for `embeddinggemma` but rank 5 for `bge-m3`.
  - `tesla-a1`: rank 6 and 8 under C1. Under C7 both are found: `tesla-a1` at rank 1 for `embeddinggemma` and 2 for `bge-m3`, `tesla-a3` at rank 7 and 2.
- **Indexing time,** full dev pool of about 185–192k stored tokens: `embeddinggemma` 31 s for C1 and 28 s for C3; `bge-m3` 71 s and 81 s, so about 2.5x slower. The C7 times (10.5 s and 27.4 s) are **not** cold-cache: 257 of its 454 chunks were identical to chunks already cached, so only 197 were embedded.

**Caveat on C7's dev numbers.** The C7 detector rules (the labelled-row minimum, the title-line limit and the "Table N" stop) were adjusted on the dev documents while checking where the dev table gold rows fall in C7 chunks. That check used the 15 new dev table questions. C7's clean-table score of 1.000 on dev is therefore **optimistic** and is not evidence that C7 beats C1. Only the single held-out test run can show that. C1, C3 and the embedding comparison weren't tuned this way.

### Step 5: dev optimizer run, registry, B (2026-11-04)

**Built:**
- **Registry:** `optimizer/registry.py`, with migration `003_registry.sql` adding the `chunking_registry` and `optimization_runs` tables.
  - Matching: the format, reliable-headings flag, tables flag and language must be equal.
    - Strong match: table share within 0.02, and heading density, characters per page and median section tokens each within 1.5x.
    - Borderline match: within 0.05 and 2.5x.
    - These tolerances were fixed before regret was measured.
  - Reuse needs the same embedding model, digest, prompt version, extractor version and chunker version. Entries that differ are marked stale.
- **Cheap re-test:** `retest_config`, 10 questions comparing the cached config with C1. The cached config is kept unless C1 is clearly better.
- **Ingestion:** `optimizer/choose.py` is wired into `ingest.py`. The `chunking` setting is `adaptive` (default), `fixed` (Stage 2; used by test fixtures and the Stage 3 runner), or `C1`–`C7`. Every ingest writes an `optimization_runs` row.
- **Tests:** 8 in `tests/test_registry.py`. Full suite: 243 passed. `ruff` is clean.

**Dev optimizer run** (`benchmarks/results/optimize_dev_20261104/`, embeddings not cached, so timings are cold):

| Document | Ingest total | Question generation | LLM calls | Accepted (target 40) | Candidates | Extract | Index winner |
|---|---|---|---|---|---|---|---|
| Tesla 10-K | 608 s | 511 s | 39 | 14 (1 table) | 60 s | 13.1 s | 21.9 s |
| NIST AI RMF | 556 s | 507 s | 44 | 26 | 39 s | 3.5 s | 3.9 s |
| Ragas | 529 s | 507 s | 41 | 19 | 18 s | 0.5 s | 1.8 s |
| Fed MPR, Feb 2025 | 560 s | 506 s | 38 | 16 (0 table) | 38 s | 4.7 s | 9.3 s |

- **Ingest takes 8.8–10.1 minutes per document.** About 90% is question generation, which hit its time cap (70% of 12 minutes) on every document.
- **LLM calls average 11.5–13.3 s each,** against the smoke test's 5.6 s median on short passages. The 5–9 minute estimate in the plan was too low, and the 40-question target is never reached within the cap.
- **Acceptance is 35–59%.** Rejections are mostly "quote not found" (11–16 per document) and "copies the quote's wording" (5–9). Table questions came out at 1 on Tesla and 0 on Fed, although the plan asked for at least 3 on Tesla. Rejected outputs weren't saved, so the cause isn't diagnosed.
- **Bug found and fixed:** the split took its 10 confirmation questions first, so Tesla had only 4 selection questions, Fed 6 and Ragas 9. All three fell below the 10-question minimum and kept C1 automatically. The split now gives confirmation at most a quarter of the questions, with a test.
- **Selection re-applied offline** to the saved scores with the corrected split (no new LLM calls). **C1 still wins on all 4 documents.** Selection/confirmation counts: Tesla 11/3, NIST 20/6, Ragas 15/4, Fed 12/4.
  - Tesla: all six scored candidates are tied, with the leader at 1.000 (C2 and C6).
  - NIST: C2 leads at 0.892 against C1's 0.800, with a CI from −0.265 to +0.052, so they are tied.
  - Ragas: C1 leads.
  - Fed: every candidate scores 1.000 or 0.999. The sampled pool is small (25–61 chunks), so the questions are too easy to tell candidates apart.

**B, on the 44 dev benchmark questions.** All 7 candidates were applied globally; the selection rule picks the simplest tied candidate.
- **B = C1.** C7 leads with Recall@budget 0.955. C1 scores 0.841, and C1 minus C7 is −0.114 (−0.227 to 0.000).
- That interval's upper end is exactly zero, so by the rule it is a tie, and the simplest wins. It sits on the boundary.
- C7's lead is also optimistic, because its detector was tuned on dev (decision 41).
- C6 scores 0.954, C2 0.908, C3 0.886, C5 0.841, and C4 0.727 (clearly worse).

**A vs B vs C on dev:** identical, since all three are C1. Recall@budget is 0.841 on all 44 questions and 0.722 on the 18 clean table questions; the 2 extraction failures score 1.000.

**Regret, leave-one-out (anecdotal, 4 documents):**
- **The registry finds no match for any dev document,** so every document would get a full optimization.
- The profiles differ in structure: the reliable-headings flag (Tesla and Fed no; NIST and Ragas yes) and the tables flag (NIST has none; Ragas has one small table).
- Forced-nearest reuse loses 0.0 everywhere, but only because every winner is C1.
- **Regret can't be measured meaningfully on this dev set.**

### Stage 4 findings: optimizer weaknesses (recorded 2026-11-04, not tuned further this stage)

By the user's decision (43), the optimizer is reported as built and measured, and is not tuned further in Stage 4.

1. **Ingest takes about 10 minutes per document** (8.8–10.1 min measured, cold). About 90% is question generation, which hit its time cap on all 4 dev documents. LLM calls averaged 11.5–13.3 s, against the 5.6 s from the smoke test.
2. **Only 14–26 questions are accepted against a target of 40,** an acceptance rate of 35–59%. Most rejections are "quote not found" (11–16 per document) and "copies the quote's wording" (5–9). Rejected outputs weren't saved, so the cause isn't diagnosed.
3. **Only 0–1 table questions are accepted per table-heavy document** (Tesla 1, Fed 0), although the plan asked for at least 3 on Tesla. The optimizer barely tests what C7 is for.
4. **Scores saturate on small sampled pools.** Candidates are scored only on chunks touching the sample (25–134 chunks), so most of them score about 1.0 (Fed, Tesla) and can't be told apart. With 11–20 selection questions, every difference is a tie, so C1 wins every time.
5. **The registry can't show reuse on this dev set.** The structural flags (reliable headings; any detected table) differ between all 4 dev documents, so leave-one-out finds no match and regret can't be measured.

Candidate fixes for a later stage, not done:
- Score on the whole document's chunks.
- Save and diagnose rejected questions.
- Shorten generation output, or allow more time.
- Use a table-share threshold instead of "any table" for matching (open question).

### Held-out comparison, pre-registered 2026-11-04, before any Stage 4 test result

Decision 42, the user's design. It replaces the planned B-vs-C comparison, because on dev A, B and C are all C1.

- **Systems,** each one run on all 5 test documents, in its own index folder:
  - **A:** `--chunking C1`, fixed 512/50. It is chunked identically to Stage 3's system A but re-indexed fresh at the frozen commit.
  - **C7:** `--chunking C7`, table-aware 512/50, as one fixed config for every document.
  - **C:** `--chunking adaptive`, the per-document optimizer with the default caps. The registry starts empty in C's folder. Test documents are ingested in manifest order (Apple, Fed, NIST CSF, RAPTOR, best practices), and reuse between test documents is allowed, as it would be in real use.
- **Common setup:** `embeddinggemma:300m` embeddings, `qwen3.5:9b` answers, top-5, a 4,000-token evidence maximum, Recall@budget at 2560 evidence tokens (C7 header context charged), a retrieval pool of 30, and the score gate off during runs. Judge: `gemma4:e4b` with `audit-1` and `loose-1`, plus the gold comparison.
- **Questions:** `benchmarks/questions_test.yaml`, unedited, SHA-256 `521c907c82941113…`. There are 30 questions: 24 answerable, including **6 table questions**, and 6 unanswerable. Gold for `fed-01` and `apple-06` stays narrow, as decided in Stage 3.
- **Primary questions:**
  1. Does C7 beat A on test **table** questions (n = 6)?
  2. Does C7 beat A on **all 24 answerable** questions?
- **Metric and rule:** Recall@budget. Paired bootstrap 95% CI of C7 minus A (10,000 resamples, seed 13). If the CI is entirely above 0, C7 is better; if entirely below, C7 is worse; if it includes 0, the result is **inconclusive**. With n = 6, an inconclusive table result is likely, and it will be reported as such.
- **Secondary, descriptive:**
  - C minus A and C minus C7 on the same metric.
  - Hit@5 and MRR.
  - Answer-level results: gold-comparison conflicts, citations off gold, judge flags, and refusals of the 6 unanswerable questions.
  - What happens to `bp-03` and `fed-02`.
  - Latency.
  - Ingest time per test document for C, and C's per-document choices.
  - The Fed report's numbers, with a post-hoc breakdown by code after the run.
- **Procedure:**
  - Run A, then C7, then C, each once with `--final` and the judge.
  - A crash is continued with `--resume`, never rerun from scratch.
  - No code changes between the runs: all three must record the same commit.
  - No retuning after seeing results.
- **Reporting:** C7's dev scores are optimistic, because its detector was tuned on dev (decision 41). The held-out result is the only evidence for C7, and whatever it shows will be reported.

### Held-out run: arms complete; C = A by construction (2026-11-04)

The run resumed at 13:31 from the commands in "Held-out run: paused" below. Checked before resuming: HEAD `b386cd9`, no diff in `src/` or `tests/`, model digests unchanged. All runs record `b386cd9+uncommitted`, because the only uncommitted files were `docs/PROGRESS.md` and the A results file; the code was frozen.

| Arm | Flag | Result | Finished |
|---|---|---|---|
| A | `--chunking C1` | Complete: 30 answered, 30 judged. `benchmarks/results/test_embeddinggemma_300m_C1_20261104T064322.json` | 13:41 |
| C7 | `--chunking C7` | Complete: 30 answered, 30 judged. `benchmarks/results/test_embeddinggemma_300m_C7_20261104T081208.json` | 14:15 |
| C | `--chunking adaptive` | Ingestion complete, then stopped at 15:03:32, after document 5 reached `ready` and **before any question was answered**. No results file; 0 query traces | 15:03 |

**C's result: per-document choices and ingest times.** The optimizer's own timings come from `optimization_runs` in `data/eval/test_embeddinggemma_300m_adaptive/`. No scores are reported here.

| Test document | Action | Chosen | Optimizer time | LLM calls | Questions accepted (selection + confirmation) | Table questions | Why C1 |
|---|---|---|---|---|---|---|---|
| Apple 10-K | optimize | **C1** | 565 s | 30 | 9 + 3 | 2 | Only 9 selection questions, so the control is kept |
| Fed MPR, June 2025 | optimize | **C1** | 545 s | 32 | 6 + 2 | 1 | Only 6 selection questions |
| NIST CSF 2.0 | optimize | **C1** | 537 s | 40 | 15 + 4 | 0 | C3 led; tied with C1, so the simplest wins |
| RAPTOR | optimize | **C1** | 572 s | 28 | 7 + 2 | 2 | Only 7 selection questions |
| Best practices (RAG) | optimize | **C1** | 584 s | 29 | 15 + 4 | 5 | C6 led; tied with C1, so the simplest wins |

- **Question generation stopped at its time cap on every document,** after 505–519 s, the 70% share of the 12-minute budget. Calls averaged about 13–18 s, slower than dev's 11.5–13.3 s.
- **The registry never matched:** every document ran a full optimization. The registry started empty in this folder, and no later test document matched an earlier one.
- The Stage 4 findings (decision 43) hold on held-out documents too.

**Why C = A, by construction:**
- **Same chunks.** All 5 documents in C's index have chunking config `fixed/512/50/fixed-1`, the same file hash and extractor version as A, and identical chunk lists: index, offsets, text, and zero context tokens. That's 193, 88, 29, 43 and 46 chunks.
- **Same retrieval.** The embedding model, its digest and the embedding input are the same, so retrieval is the same.
- **Same answers, as far as evidence shows.** Generation was shown deterministic in Stage 3: the 2026-11-03 rerun matched the 2026-10-30 answers word for word on all 39 dev questions. That wasn't re-verified for this run, because C wasn't answered.
- **Reporting:** C's held-out metrics are A's. C minus A is zero by construction, and C minus C7 equals A minus C7.

**Analysis still to do** (not started; no test metric has been opened):
- Run the pre-registered report: `python data/eval/stage4_test_report.py <A file> <C7 file> <A file>`. Pass A's file as C, since C = A.
- Report the primary C7-vs-A result first: table questions (n = 6), then all 24 answerable.
- Then C (= A), with the choices above, then the post-hoc Fed breakdown.
- Before committing, move the script into `benchmarks/analysis/` and ask the user.

### Held-out run: paused 2026-11-04, 12:33 (user's request)

The run was stopped cleanly by stopping the background job. No runner process remains. Results are saved after every question and every judge call, so nothing is lost or half-written.

**Where it stopped:**

| Arm | Flag | State | Results file |
|---|---|---|---|
| A | `--chunking C1` | **All 30 questions answered and saved.** Judge pass: 8 of 30 rows done (`apple-01` … `apple-06`, `apple-un`, `apple-un2`); **next is `fed-01`**. The other 22 rows aren't judged yet: 18 answered or partial, and 4 unanswerable, which the judge skips. Metadata says `complete: false`; recorded commit `b386cd9` | `benchmarks/results/test_embeddinggemma_300m_C1_20261104T064322.json` |
| C7 | `--chunking C7` | Not started. No results file, no index folder | none |
| C | `--chunking adaptive` | Not started. No results file, no index folder | none |

- **A's index:** `data/eval/test_embeddinggemma_300m_C1/`, all 5 test documents `ready`. A resume reuses it.
- **Started:** A at 12:12:34. Answering took about 20 minutes for 30 questions.
- **Nothing analysed:** no Stage 4 test metric has been looked at.

**Before resuming,** check the code is still frozen:

```
git diff --stat b386cd9 -- src tests     # must print nothing
```

- The untracked A results file, and this PROGRESS.md edit, make `git status` dirty. Resumed and new runs will therefore record `b386cd9+uncommitted`. For A, the runner adds it under `resumed_commits` and keeps `commit: b386cd9`.
- The code is unchanged, so this is a docs-and-results difference only. Note it in the report. Ask the user before committing anything, which would change the hash.

**Resume commands,** from the repo root, with the conda env `adaptive-rag`, in this order:

```
SRC='30 test questions written by Claude in a separate chat session; 5 spot-checked against the PDFs by the user; not human-written'
NOTES='Stage 4 pre-registered held-out run (decision 42)'

# 1. Finish arm A: skips the 30 answered questions and the 8 judged rows, judges the rest.
python -m adaptive_rag.evaluation run --set test --questions benchmarks/questions_test.yaml \
  --judge --final --chunking C1 --question-source "$SRC" --notes "$NOTES" \
  --resume benchmarks/results/test_embeddinggemma_300m_C1_20261104T064322.json

# 2. Arm C7: a fresh start, since nothing was saved.
python -m adaptive_rag.evaluation run --set test --questions benchmarks/questions_test.yaml \
  --judge --final --chunking C7 --question-source "$SRC" --notes "$NOTES"

# 3. Arm C: a fresh start. Its optimizer runs at ingest, about 10 minutes per document.
python -m adaptive_rag.evaluation run --set test --questions benchmarks/questions_test.yaml \
  --judge --final --chunking adaptive --question-source "$SRC" --notes "$NOTES"
```

- **If arm C7 or C stops again:** rerun the same command with `--resume <file>`, using the path it printed on its `Saving progress to …` line.
- **If arm C stops before that line appears,** it stopped during ingestion: no results file exists yet, and a document may be left mid-index. Don't delete its index folder without asking the user. Inspect the `documents` status in `data/eval/test_embeddinggemma_300m_adaptive/adaptive_rag.sqlite` first.
- **Time left, estimated from Stage 3 and dev timings (not measured):** A's judge pass about 5–10 minutes, C7 about 25–30 minutes, C about 75–80 minutes.
- **After all three finish:** analyse with `stage4_test_report.py`. It is kept in the gitignored `data/eval/stage4_test_report.py`, so it doesn't mark the tree dirty during the runs; move it to `benchmarks/analysis/` after the runs. Run it as `python <script> <A results> <C7 results> <C results>`. Report in the pre-registered order.

### Held-out results (2026-11-04), as pre-registered (decision 42)

Report: `benchmarks/results/stage4_test_report_20261104T093653.json`, from `benchmarks/analysis/stage4_test_report.py`.
- **Inputs:** A `test_embeddinggemma_300m_C1_20261104T064322.json` and C7 `test_embeddinggemma_300m_C7_20261104T081208.json`, with A's file standing in for C.
- **Commits:** A recorded `b386cd9`, and C7 `b386cd9+uncommitted`. The only uncommitted files were docs and results; the code was frozen.
- **Questions:** 30: 24 answerable (6 table) and 6 unanswerable.

**Primary: C7 minus A, paired bootstrap 95% CI:**

| Subset | Metric | A | C7 | C7 − A | Verdict |
|---|---|---|---|---|---|
| Table (n = 6) | **Recall@budget** | 0.833 | 1.000 | **+0.167 (0.000 to +0.500)** | **Inconclusive** (CI includes 0) |
| Table (n = 6) | Hit@5 | 0.833 | 0.833 | 0.000 (−0.500 to +0.500) | Inconclusive |
| Table (n = 6) | MRR | 0.617 | 0.444 | −0.172 (−0.500 to +0.133) | Inconclusive |
| All answerable (n = 24) | **Recall@budget** | 0.860 | 0.860 | **0.000 (−0.125 to +0.125)** | **Inconclusive** |
| All answerable (n = 24) | Hit@5 | 0.875 | 0.833 | −0.042 (−0.167 to +0.083) | Inconclusive |
| All answerable (n = 24) | MRR | 0.716 | 0.643 | −0.074 (−0.217 to +0.067) | Inconclusive |

**On held-out data, C7 is not shown to beat A,** on table questions or overall. The table gain is one question (`fed-02`), and the interval's lower end is exactly 0. C7's dev scores, including 1.000 on clean dev table questions, were optimistic as expected (decision 41).

**Question by question:** 14 of 24 answerable questions differ in at least one metric, status or verdict.
- **C7's gain:** `fed-02` (table). Gold was at rank 6 with Recall@budget 0 under A; under C7 it is at rank 3 with Recall@budget 1.
- **C7's losses:**
  - `raptor-01` (factual): gold rank 2 → 7, answered → **insufficient**. This is a new false refusal; A answered it correctly.
  - `raptor-03` (table): rank 1 → 6, so it loses Hit@5. Recall@budget stays 1.0 because C7's smaller chunks fit more into the budget.
- **Rank changes with the same outcome:** `apple-01`, `apple-02`, `apple-03`, `fed-01`, `fed-03`, `csf-01`, `csf-03`, `csf-04`, `csf-05` and `bp-04`, some up and some down.
- **Confound:** C7 also chunks *prose* differently, recursively rather than fixed. The losses on non-table questions such as `raptor-01` come from that, not from table handling. This run can't separate the table effect from the recursive-prose effect.

**Answers:**
- **A's answers match Stage 3's answers word for word, and retrieval is identical, on all 30 test questions.** So the user's Stage 3 labels apply to A unchanged: `bp-03` and `fed-02` are wrong, the other 6 labelled answers correct.

| Measure | A | C7 |
|---|---|---|
| Answerable: answered / partial / insufficient | 23 / 1 / 0 | 23 / 0 / 1 (`raptor-01`) |
| Gold comparison: conflicts | 2 (`bp-03`, `fed-02`) | 2 (`bp-03`, `fed-02`) |
| Citation off gold | 3 | 3 |
| Judge: off topic | 2 | 2 |
| Faithfulness (judge) | 0.882 (0.771–0.965) | 0.909 (0.801–0.986) |
| Unanswerable refused | 6 of 6 | 6 of 6 |
| Generation p50 / p95 | 32.1 s / 37.9 s | 32.3 s / 40.1 s |
| Average input tokens | 3,151 | 2,517 (−20%) |

- **`bp-03`** is wrong under both systems, retrieved at rank 1 both times. A gives 94.26 for 512 tokens; C7 gives 94.26 for 1024. The gold answer is 97.59. This is a reading error from the right table, which chunking doesn't fix.
- **`fed-02`** is wrong under both. A missed the table (partial answer, 2.1%). C7 retrieved it but answered 3.0% for both values. **C7 turned a retrieval miss into a reading error.** This fits the flattened Fed Table 1 header (decision 39).
- **`apple-06`:** the gold comparison moves from conflicts (A) to agrees (C7). The Stage 3 user label marked A's answer correct with narrow gold, so this isn't a C7 correctness gain.
- **C7's answers have no user labels.** Its wrong-answer count rests on the gold comparison.

**C = A:**
- **Same chunks:** chunks are identical for all 5 documents.
- **Same answers:** A matches Stage 3 word for word (above), so generation is deterministic on held-out data.
- C's per-document choices and ingest times are in the table under "Held-out run: arms complete". The optimizer chose C1 for all 5, at 537–584 s per document.

**Post-hoc Fed breakdown** (test `fed_mpr.pdf`). Computed by code after the run, and not used for tuning:

| ID | Type | A: R@b / gold rank | C7: R@b / gold rank | Gold inside one chunk (A / C7) | Answer (gold comparison, A / C7) | Reading |
|---|---|---|---|---|---|---|
| `fed-01` | factual | 0.00 / 6 | 0.00 / 9 | yes / yes | agrees / agrees | Gold too narrow (Stage 3 label: correct answer from another passage) |
| `fed-02` | table | 0.00 / 6 | 1.00 / 3 | yes / yes | conflicts / conflicts | Table retrieval miss under A; under C7 the table is found but misread (flattened header) |
| `fed-03` | conceptual | 1.00 / 1 | 1.00 / 2 | yes / yes | agrees / agrees | Fine |
| `fed-04` | multi_part | 0.64 / 2 | 0.64 / 2 | yes / yes | agrees / agrees | One of two evidence parts not retrieved |
| `fed-05` | factual | 1.00 / 1 | 1.00 / 1 | yes / yes | agrees / agrees | Fine |
| `fed-un` | near_miss | n/a | n/a | n/a | refused / refused | Correct refusal |

- **Fed Recall@budget:** A 0.53, the same as Stage 3; C7 0.73 by the same per-question values.
- **No Fed gold span is split by a chunk boundary** under either system, so boundaries aren't the cause.
- **The three causes:**
  1. Narrow gold (`fed-01`), a benchmark artefact.
  2. A table retrieval miss (`fed-02`), which C7 fixes for retrieval only.
  3. Partial multi-part coverage (`fed-04`), a retrieval-depth problem for Stage 5.
- **This is post-hoc, on 5 questions.** Treat it as hypotheses only.

### Stage 4 summary

**Built:**
- Chunkers: recursive (C2–C4), structure-aware (C5), semantic (C6), and the table detector with table-aware chunking (C7).
- Context-token charging in every budget.
- Profiler, sampling, in-memory scoring, the selection rule and caps, embedding cache.
- Configuration registry with reuse, cheap re-test and staleness, wired into ingestion through the `chunking` setting.
- Page-aware quote location, and the runner's `--chunking` systems.
- 246 tests passing, `ruff` clean.

**Measured:**
- **`bge-m3` retest:** keep `embeddinggemma:300m` (0 of 3 configs favoured `bge-m3`).
- **Optimizer cost:** about 9–10 minutes per document, on both dev and test.
- **Optimizer choices:** it picked C1 for all 9 documents, dev and test. B = C1 on dev.
- **Held-out:** C7 vs A is inconclusive on table questions and overall, and C = A.

**Not shown:** that per-document optimization or table-aware chunking improves retrieval or answers on held-out data.

**Limitations:**
- Only 6 table test questions.
- C7's detector was tuned on dev.
- C7 changes prose chunking as well as tables (a confound).
- Table extraction flattens headers.
- Optimizer weaknesses, under decision 43.
- Regret couldn't be measured.
- C7's test answers have no human labels.

## Stage 5 progress

### Dev multi-part questions (2026-11-04)

- `benchmarks/questions_dev_multipart.yaml`: 12 questions (3 per dev document; 8 with 2 parts, 4 with 3), written in a separate Claude session from `data/dev_multipart_prompt.txt`. **The user said they spot-checked some, but didn't name which IDs**; record them here when given.
- Validation: 11 of 12 passed first time. `mp-ragas-01`'s URL quote wasn't found: the loader breaks the URL at `github.com/` and joins the footnote marker to "Ragas". Shortened to `explodinggradients/ragas.` under decision 38, with a note; question and answer unchanged.
- Overlap with test (`question_overlap_20261104T112837.json`, Stage 4 thresholds): **0 of 12 flagged.** Closest: `mp-fed-01` vs test `fed-02`, cosine 0.817 (both about PCE in the projections table of two editions). `fed-02` is already "seen".

### Dev baseline A, retrieval only (2026-11-04)

C1, top-5, index `data/eval/dev_embeddinggemma_300m_C1/` (all 4 dev documents). Ollama is now 0.40.14 (was 0.40.13); digests unchanged.

| Set | n | Recall@budget (2560) | Hit@5 | MRR | Part coverage | All parts covered |
|---|---|---|---|---|---|---|
| Dev (`questions_dev.yaml`) | 29 | 0.862 (0.724–0.966) | 0.862 | 0.661 | n/a | n/a |
| Dev tables | 15 | 0.800 (0.600–1.000) | 0.800 | 0.478 | n/a | n/a |
| Dev multi-part | 12 | 0.810 (0.706–0.914) | 1.000 | 0.785 | 0.750 (0.625–0.875) | 5 of 12 |

- Dev matches Stage 3's 2026-11-03 run exactly on all 36 shared answerable and near-miss questions. Only the 3 out-of-scope top scores changed (max +0.054, still below 0.25), because this index also holds the Fed Feb 2025 report. So 0.40.14 gives the same embeddings.
- **Regression check:** after the build, A on dev reproduces every rank metric on all 66 questions, and recall over sent evidence equals Recall@budget on every question. That backs reusing Stage 4's A file (decision 48).

### Built (2026-11-04)

- `retrieval/query.py`: rule-based type and part splitting (lead-ins merged forward). On dev: 12 of 12 multi-part split, 1 of 15 table and 2 of 39 other questions split.
- `retrieval/adaptive.py`: per-part pools, coverage-first, dynamic depth (floor, delta, min/max), dedupe, neighbors, budget. `retrieval/evidence.py`: one entry point for answering and evaluation.
- Prompt switches: table-reading rule (`table_prompt`), uncovered-part notice. Trace column `retrieval` (migration 004).
- Metrics: part coverage, recall and part coverage over sent evidence, tokens sent. Runner flags `--retrieval adaptive` and `--table-prompt`.
- Defaults unchanged: `retrieval = "baseline"`, `table_prompt = False`. 271 tests pass, `ruff` clean.

### Dev sweep, retrieval only (`stage5_sweep_20261104T114134.json`, rule = decision 49)

192 configs: budget {2500, 2560, 4000} × split × delta {off, .05, .10, .15} × multi-part max {5, 8} × dedupe × neighbors. A = 0.834 recall sent over 56 answerable dev questions, 2545 tokens.

| System | Recall sent | Tables | Part coverage | All parts | Tokens | vs A (95% CI) |
|---|---|---|---|---|---|---|
| Best at 2500 | 0.808 | | 0.722 | 5/12 | 1905 | −0.026 (−0.089 to +0.036) |
| Best at 2560 (split, δ .05, neighbors) | 0.838 | 0.800 | 0.750 | 5/12 | 2233 | +0.003 (−0.050 to +0.057) |
| Best at 4000 (split, δ .10, neighbors) | 0.873 | 0.850 | 0.750 | 5/12 | 3019 | +0.039 (0.000 to +0.092) |
| Plain top-7 at 4000 (control) | 0.859 | 0.800 | 0.792 | 6/12 | 3569 | +0.025 (0.000 to +0.068) |

- **At equal budget S ≈ A.** At 4000, most of the gain is from more tokens: S minus plain top-7 is +0.014 (−0.018 to +0.057).
- **2500 fits only 4 C1 chunks** (373 of 377 dev chunks are 512 tokens), so S at 2500 has one chunk less than A. The plan's "2500 equals A's ~2560" was wrong.
- Ablation: dedupe removes 0 tokens on dev (no near-duplicates selected); multi-part max has no effect; splitting adds +0.003–0.004; **neighbors are the only feature with a clear effect** (+0.035 at 4000).
- **Why splitting doesn't help:** the parts that are missed are mostly not top-1 even for their own sub-query. 5 of 7 missed parts are **table rows** (Lathrop, Automotive sales, MAP 1.5, PCE and Unemployment projection rows), at rank 5–24 or beyond 30 under dense search. Part queries also lose context ("where do FOMC participants see *it*").
- **Offline BM25 check** (in-memory FTS5, not built into the product): reaches 2 of 7 missed parts (Lathrop rank 1, oversight aside rank 2); the rest stay at rank 7–23 or beyond 30. Over all 72 dev gold facts, BM25 by part gets 52 into the top 5.

## Workspace state

- **Branches:** `main` has Stages 2–4 (Stage 4 merged 2026-11-04, not pushed). `stage-4-chunking-optimization` is kept. Commit only when the user asks.
- **Environment:** conda env `adaptive-rag` (Python 3.11.18), with the project installed in editable mode.
- **Ollama 0.40.13.** Models installed: `embeddinggemma:300m` (`85462619ee72`), `qwen3.5:9b` (`6488c96fa5fa`), `gemma4:e4b` (`c6eb396dbd59`), `bge-m3:latest` (kept, but not used after decision 40), and `deepseek-r1:8b`. `qwen3.5:4b` is not installed.
- **Data folders under `data/eval/`** (all gitignored):
  - `dev_*` folders and `test_embeddinggemma_300m/` from Stage 3.
  - `embcache/`, the Stage 4 embedding cache for dev.
  - `test_embeddinggemma_300m_C1/`, `_C7/` and `_adaptive/` hold the Stage 4 held-out indexes, each with all 5 documents ready. `_adaptive/` also holds C's registry and `optimization_runs`.
- **PDFs:** benchmark PDFs, including `dev/fed_mpr_feb2025.pdf`, are in the gitignored `benchmarks/documents/`.
- **Test set:** `benchmarks/questions_test.yaml` is tracked. This assistant has not read the test questions' text or the test documents' content; only IDs, counts and hashes were used.
- No evaluation process is running and no models are loaded. The held-out analysis is done.

## Next steps

1. **User:** run the separate Claude session with `data/dev_multipart_prompt.txt`, spot-check a few of the 12 questions against the PDFs, and say when `benchmarks/questions_dev_multipart.yaml` is in.
2. **Then:** validate the file, run the overlap check against test questions (IDs and scores only), and record a dev baseline (A, retrieval-only) on all dev sets, including part coverage.
3. **Build** in `retrieval/`, each feature behind its own switch: query analysis and splitting, per-part retrieval, dynamic depth, dedupe, neighbors, part-aware evidence check, table-reading prompt. Plus the regression test for A, and metrics for recall over sent evidence, part coverage and duplicate tokens removed.
4. **Tune on dev:** retrieval-only sweeps first; answer runs only for finalists (A, S with table prompt off, S with it on), about 30–35 min each.
5. **Pre-register** the held-out A vs S comparison in this file and freeze it by commit (decision 48). Primary: S − A on Recall over sent evidence, all 24 answerable, paired bootstrap CI must exclude 0. Secondary: part coverage on the 4 multi-part (descriptive), gold-comparison correctness on the 6 table questions. Guardrails: 6 of 6 refusals, false refusals and p50 latency. Seen questions shown with and without.
6. **Don't rerun the held-out test set** except for that one pre-registered run.

## Open questions

- Stage 8: build a human-written test subset before quoting final numbers publicly? Deferred by the user on 2026-11-04.
- Registry matching: should "has tables" mean any detected table, or table share above about 2%? Deferred: no optimizer tuning in Stage 4.
