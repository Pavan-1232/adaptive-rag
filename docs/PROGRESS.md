# Adaptive RAG: Progress

**Last updated:** 2026-11-09
**Current state:** Stage 5b exact lookups on by default (2026-11-09). Stage 8 on `main`, pushed to the **public** repo https://github.com/Pavan-1232/adaptive-rag (pushed while private on 2026-11-09, since made public): CI green, README images and links checked. History rewritten (noreply author, copied document text removed), old repo deleted, local history cleaned. Before going public: enable private vulnerability reporting. Human-written test subset deferred (2026-11-09).
**v1.1 held-out run not done; v1.1 features are measured on dev and the private real-use set only.**

The approved architecture is in [DESIGN.md](DESIGN.md).

## Stage status

| Stage | Name | Status |
|---|---|---|
| 1 | Design | Complete; approved 2026-10-30 |
| 2 | Baseline backend | Complete and committed 2026-10-30 |
| 3 | Evaluation harness | Complete; approved 2026-11-04 |
| 4 | Chunking optimization | Complete; approved 2026-11-04 |
| 5 | Adaptive retrieval | Complete; approved 2026-11-05. Adaptive retrieval is opt-in (decision 57) |
| 5b | Table extraction | Deferred; top future-work item (decision 58) |
| 6 | BYOK | Complete; approved 2026-11-06. Gemini verified with a real key; OpenAI and Anthropic by mocked tests only (decision 65) |
| 7 | Frontend | Complete; merged into `main` 2026-11-06 at the user's request |
| 8 | GitHub polish | Plan approved 2026-11-06; in progress |

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
| 50 | Held-out S uses a 2,560-token budget, to match A. 4,000 is reported only as a trade-off | 2026-11-05 |
| 51 | Audit of DESIGN.md section 6: build the missing items behind switches (gap cutoff, span merging, per-document cap and comparative type, neighbor reserve and block merging, table rule only when a table is in the evidence) | 2026-11-05 |
| 52 | Hybrid keyword + vector search (SQLite FTS5) behind its own switch, time-boxed, tuned on dev only; off if it doesn't help | 2026-11-05 |
| 53 | Hybrid keyword search **off** for S: recall within 0.002 of the hybrid version, simpler, and hybrid loses `tbl-fed-05`. It stays an opt-in switch (`adaptive_hybrid`) | 2026-11-05 |
| 54 | Neighbor reserve **0** for S. This is a measured deviation from DESIGN.md's 30%: the 30% reserve was swept on dev and lowered recall at 2560 (0.854 → 0.834). The reserve stays a setting | 2026-11-05 |
| 55 | `config.py`'s `adaptive_*` defaults and `evidence_target_tokens` (2560) are set to finalist S, so `--retrieval adaptive` runs exactly S without environment variables. `retrieval` stays `"baseline"` by default, so product behaviour is unchanged until the held-out result | 2026-11-05 |
| 56 | Stage 5 held-out comparison pre-registered: A (Stage 4's C1 file) vs S at 2,560 tokens. Primary: S minus A on recall over sent evidence, all 24 answerable, paired 95% CI must exclude 0. Details under "Held-out comparison, pre-registered 2026-11-05" | 2026-11-05 |
| 57 | `retrieval = "baseline"` stays the product default. Adaptive retrieval stays opt-in, with all its switches. Finding: S vs A is inconclusive (−0.019, CI −0.144 to +0.106); S sends 11% fewer tokens and passes every guardrail. Its losses come from the gap cutoff (`csf-03`) and part splitting (`csf-04`). The `bp-03` gain isn't attributable to retrieval (same recall, different prompt) | 2026-11-05 |
| 58 | Stage 5 approved. Stage 5b (table extraction) is deferred and is the **top future-work item**: `fed-02` still fails on the flattened Fed table header even when the table is retrieved | 2026-11-05 |
| 59 | Stage 6 plan approved: (1) direct `httpx` adapters, no SDKs; (2) cloud for answering only, with embeddings, optimizer and judge staying local; (3) keys from `.env` or the environment only in this stage | 2026-11-06 |
| 60 | Stage 7 must let users enter their own API keys in the UI, stored securely on the local machine (for example the OS keychain), never as plain text in the database or logs. Stage 6 loads keys through one function, so a keychain source can be added without changing the adapters | 2026-11-06 |
| 61 | Cost-sensitive default cloud models, checked against each provider's docs on 2026-11-06 and set in `config.py`: OpenAI `gpt-6-luna` ($0.10 / $0.50 per 1M tokens), Gemini `gemini-3.5-flash-lite` (stable; price not shown in the docs fetched), Anthropic `claude-haiku-5-5` ($0.10 / $0.50) | 2026-11-06 |
| 62 | CLAUDE.md rule added: no shortcuts in security code (key handling, logging, traces, error messages, storage). Any `shortcut:` there is flagged to the user first | 2026-11-06 |
| 63 | Stage 6 build choices, from the 2026-11-06 docs check: Gemini uses `generateContent` (the current reference), with the key in `x-goog-api-key`, not `?key=`. Anthropic sends `anthropic-version: 2026-10-21` and `output_config.effort = "low"`. No cloud adapter sends `temperature` | 2026-11-06 |
| 64 | Keys are also read from the standard variables `OPENAI_API_KEY`, `GEMINI_API_KEY` and `ANTHROPIC_API_KEY`, as well as the `ADAPTIVE_RAG_` names. Cloud use still needs the request's `provider` plus the knowledge base's `allow_cloud` | 2026-11-06 |
| 65 | Stage 6 approved. Verification level: **Gemini verified end to end with a real key** (2 calls on `gemini-3.5-flash-lite`); **OpenAI and Anthropic verified by mocked contract tests only**, with no real calls | 2026-11-06 |
| 66 | Stage 7 plan approved: (1) build the frontend directly, no Lovable code (Lovable screenshots may guide layout only); (2) same-origin serving, no CORS, with `Host` and origin checks; (3) `keyring` (OS keychain) for keys, checked before `.env` in `api_key()` | 2026-11-06 |
| 67 | Stage 7 adds deleting a knowledge base: a backend endpoint plus UI with a confirm step | 2026-11-06 |
| 68 | The key settings screen shows where each key comes from (keychain, `.env`, or not set), never the key itself. Keychain keys can be removed in the UI | 2026-11-06 |
| 69 | The evaluation view states each comparison's verdict in plain words (for example "inconclusive" or "not better than baseline") next to the numbers | 2026-11-06 |
| 70 | Stage 7 build: a changing request with **no** `Origin` and no `Sec-Fetch-Site` is accepted, since browsers always send `Origin` on POST, PATCH, PUT and DELETE, so such a request comes from a non-browser client (curl, tests) that no website can drive. Approved by the user | 2026-11-06 |
| 71 | Stage 7 build: if the keychain can't be read (locked or missing), `api_key()` falls back to `.env` and logs only the error type. Keychain write and delete failures return a fixed 503 message | 2026-11-06 |
| 72 | Stage 7 build: the UI calls `/api/...` and a middleware strips the prefix, so existing routes and tests keep their paths. `GET /evaluation` reads the two committed held-out reports at request time; verdicts come from the CI (low > 0 better, high < 0 worse, all zero identical, otherwise inconclusive) | 2026-11-06 |
| 73 | Security finding fix: Chroma runs in a separate vector-store process that never holds a key. The API starts and stops it itself (still one command). Acceptance: `test_canary_key_never_leaks_anywhere` passes at least 100 consecutive runs | 2026-11-06 |
| 74 | Benchmark content (short 10-K quotes in questions and results) stays, with clear attribution and links; no history rewrite, so the pre-registration commit hashes stay valid | 2026-11-06 |
| 75 | A 10-question human-written test subset (2 per held-out document), written by the user; retrieval-only run of A and S, reported separately as a sanity check, not run until the user's file arrives | 2026-11-06 |
| 76 | The user takes the README screenshots; the assistant specifies the screens | 2026-11-06 |
| 77 | New **private** GitHub repo for this project; the user creates it, approves the push, and makes it public later. Never push to `localdoc-rag` (public, separate Streamlit single-PDF app), which the README links as the v1 prototype | 2026-11-06 |
| 78 | MIT licence confirmed. Direct dependencies are permissive; `fpdf2` (LGPL) is test-only and not distributed | 2026-11-06 |

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

- `benchmarks/questions_dev_multipart.yaml`: 12 questions (3 per dev document; 8 with 2 parts, 4 with 3), written in a separate Claude session from `data/dev_multipart_prompt.txt`. **Not spot-checked by the user** (confirmed 2026-11-05; an earlier note said some were).
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

### Audit fixes (2026-11-05)

- Checkpoint commit `e4fd733` before any change (checked: no `data/`, `.env`, PDFs or DB files).
- Built, each behind a switch in `AdaptiveParams` and `config.py`:
  - largest-score-gap cutoff (`gap_cutoff`);
  - merging overlapping or adjacent chunks of one document into one block (`merge_spans`);
  - comparative query type and a soft per-document cap (`doc_cap`); the cap only bites while other documents still have candidates;
  - 30% neighbor reserve (`neighbor_reserve`), merged blocks ordered by best direct score;
  - table rule added only when `find_tables` detects a table in the evidence;
  - hybrid FTS5 search (`hybrid`, `keyword_weight`), migration `005_chunks_fts.sql`. Floors stay on cosine.
- Fixed: uncovered parts are now computed from the evidence actually sent.
- New tests cover the audit items, including: a part whose best chunk is dropped for budget is uncovered; neighbors never cross documents through the real DB lookup; delta off and stop reason recorded. **287 tests pass, `ruff` clean.**

### Dev sweep 2 (`stage5_sweep_20261105T114432.json`, rule = decision 49)

3,072 configs: budget {2560, 4000} × split × delta {off, .05, .10, .15} × gap × dedupe × merge × doc cap × neighbors {off, on, on with 30% reserve} × hybrid {off, .05, .10, .20}. 56 answerable dev questions. A = 0.834 recall sent.

| System | Recall sent | Tables (20) | Part coverage | All parts | Tokens | vs A (95% CI) |
|---|---|---|---|---|---|---|
| A (top-5) | 0.834 | 0.750 | 0.750 | 5/12 | 2545 | |
| **S at 2560** (split, gap, neighbors, hybrid .05) | 0.854 | 0.750 | 0.778 | 6/12 | 2361 | +0.020 (−0.036 to +0.089) |
| S at 2560 without hybrid | 0.852 | 0.800 | 0.750 | 5/12 | 2306 | +0.018 (0.000 to +0.054) |
| S at 2560 with 30% reserve | 0.834 | 0.750 | 0.750 | 5/12 | 2215 | −0.001 |
| S config at 4000 (trade-off) | 0.882 | 0.800 | 0.847 | 8/12 | 2966 | +0.048 (−0.018 to +0.123) |
| Best at 4000 (adds merge) | 0.901 | 0.850 | 0.847 | 8/12 | 3426 | +0.066 (−0.007 to +0.146) |

- Rule result at 2560: split, gap, neighbors (no reserve) and hybrid .05 stay on. Delta, dedupe, merge and doc cap have no effect on recall or coverage there, so they go off (ties go to the simpler setting). Merge saves about 93 tokens per question at equal recall.
- **The 30% reserve lowers recall at 2560** (0.854 → 0.834): it leaves room for only 3 direct chunks. The rule sets it to 0, which changes the design's starting value; needs the user's approval.
- **Hybrid is thin:** it changes 3 questions (+2, −1). Of the 7 multi-part parts A misses (5 are table rows), it recovers 1 (`mp-tesla-02`); the other 6 stay missed. It loses `tbl-fed-05`. Weights .10 and .20 are clearly worse (0.798, 0.773).
- Dev selection is optimistic: best of 1,536 configs per budget on 56 questions. The held-out run is the evidence.
- Query types on dev: 26 factual, 14 table, 12 multi-part, 4 comparative. Stop reasons for S: gap 39, max chunks 11, budget 6.

### Table-prompt test on dev (S at 2560, 15 dev table questions, gold comparison)

`dev_embeddinggemma_300m_C1_S_20261105T114552` (off) vs `..._S_tblprompt_20261105T120303` (on).

| | Off | On |
|---|---|---|
| Gold comparison agrees | 10 / 15 | 11 / 15 |
| Status answered / partial | 11 / 4 | 11 / 4 |
| Rule applied (table detected) | n/a | 10 / 15 |
| Generation p50 | 33.1 s | 38.6 s |

- The only change is `tbl-fed-01`, where the gold row isn't in the evidence (recall 0). Both answers are `partial`. "On" adds "approximately 4 percent" read off a chart description, which the judge scored as agrees. **Not a real gain, so the table prompt stays off** (decision 47).

### Finalist S (user's review, 2026-11-05)

- **Settings:** C1 chunking, `embeddinggemma:300m`, budget 2560. Splitting on, delta off, gap cutoff on, neighbors on (threshold 0.5, **reserve 0**, decision 54). **Hybrid off** (decision 53). Dedupe, merge and doc cap off; table prompt off.
- **Same as the dev run in every setting but hybrid:** these are now `config.py`'s defaults (decision 55). Checked: `AdaptiveParams.from_settings` matches the adaptive parameters recorded in `dev_embeddinggemma_300m_C1_S_20261105T114552` on every field except `hybrid`.
- **Dev result for this S** (sweep 2, the "without hybrid" row): recall over sent evidence 0.852. S minus A is +0.018 (0.000 to +0.054). Tables 0.800, part coverage 0.750, all parts covered 5 of 12, 2,306 tokens. This is selected on dev, so it's optimistic.
- **Multi-part spot-check (decision c): none.** The user confirmed on 2026-11-05 that they didn't spot-check any of the 12 dev multi-part questions. They count as written by a separate Claude session with no human check, so they are LLM-written dev data, not human-reviewed.

### Held-out comparison, pre-registered 2026-11-05, before any Stage 5 test result (decision 56)

**Systems,** both on the 5 test documents:

- **A:** reused, not rerun (decision 48). `benchmarks/results/test_embeddinggemma_300m_C1_20261104T064322.json`, SHA-256 `1cbd2e4a87043389…`, from commit `b386cd9`: C1, fixed top-5, 30 answered and 30 judged.
  - **A's recall over sent evidence is its saved `recall_at_budget`.** The two were equal on every dev question in the regression check. On test this is checked again: the retrieval-only replay of A (secondary 1) also measures A's recall over sent evidence directly. If it differs from the saved `recall_at_budget` on any question, the primary result is reported with both values for A, and the difference is named.
- **S:** `--chunking C1 --retrieval adaptive`, using `config.py`'s defaults at the freeze commit (decision 55). That is budget 2,560, part splitting on, delta off, gap cutoff on, minimum 3 chunks, maximum chunks per type {factual 5, table 5, multi-part 8, comparative 10, broad 10}, neighbors on (threshold 0.5, reserve 0), floor 0.25, pool 30, and hybrid, dedupe, merge, doc cap and table prompt all off. The uncovered-part notice is on.
  - **Index:** S reuses Stage 4's C1 test index `data/eval/test_embeddinggemma_300m_C1/`, the same chunks A used. Opening it applies migrations 004 and 005: a trace column and an FTS5 table filled from the existing chunks. The chunks are not changed.
- **Common setup:** `embeddinggemma:300m` (`85462619ee72`), `qwen3.5:9b` (`6488c96fa5fa`), and judge `gemma4:e4b` (`c6eb396dbd59`) with `audit-1`, `loose-1` and the gold comparison. Score gate off during the run. Ollama 0.40.14; A ran on 0.40.13, and dev embeddings were identical across that change.
- **Questions:** `benchmarks/questions_test.yaml`, unedited, SHA-256 `521c907c82941113…`. 30 questions: 24 answerable, including 6 table and 4 multi-part, and 6 unanswerable.

**Primary:**
- **Metric:** S minus A on **recall over sent evidence**, all **24 answerable** questions.
- **Test:** paired bootstrap 95% CI, 10,000 resamples, seed 13.
- **Verdict:** if the CI is entirely above 0, S is better; if entirely below 0, S is worse; if it includes 0, the result is **inconclusive**, and S doesn't count as beating A.

**Secondary (descriptive, no pass/fail):**
1. **Part coverage on the 4 multi-part questions:** S's part coverage over sent evidence, and the number with all parts covered.
   - A's file has no part coverage, so A's is recomputed **after** S's run by a retrieval-only replay of baseline top-5 on the same index.
   - The replay must reproduce A's saved `recall_at_budget` on all 24 answerable questions. If any question differs, A's part coverage is reported as unavailable and the mismatch is reported.
2. **Gold correctness on the 6 table questions:** the number with gold comparison "agrees", S against A's saved verdicts.

**Guardrails** (reported against these thresholds, all measured):
- **Refusals:** S must refuse **6 of 6** unanswerable questions. Fewer is a guardrail failure.
- **False refusals:** answerable questions S answers `insufficient`. A had 0.
- **Latency:** p50 generation latency, S against A's 32.1 s.

**Also reported (descriptive):**
- Tokens sent; hit@5 and MRR where defined; judge flags; citations off gold.
- **Seen questions:** `fed-02`, `fed-04` and `bp-03` are reported **separately as "seen"**, since they shaped Stage 5's focus. They stay in the primary 24, as the user specified.

**Caveats fixed now:**
- **The answer prompt differs:** Stage 5 adds the uncovered-part notice, and A's answers come from the Stage 4 prompt. Answer-level differences therefore mix a retrieval change with a prompt change. The primary metric is retrieval-only and isn't affected.
- **S was chosen on dev** as the best of 1,536 configs at 2,560 on 56 questions, so its dev gain (+0.018) is optimistic.
- **The 4,000-token budget is not run on test.** It stays a dev-only trade-off (decision 50).

**Procedure:**
- One run of S, with `--final` and the judge. A crash is continued with `--resume`, never rerun.
- No code changes during the run. New scripts stay outside the repo, or in gitignored `data/`, until it finishes.
- **The run is valid only if** its recorded `adaptive_params` match the frozen defaults above, and its recorded commit is the freeze commit.
- No retuning after seeing results. Whatever the result, it is reported.

**Command,** from the repo root with the conda env `adaptive-rag`:

```
python -m adaptive_rag.evaluation run --set test --questions benchmarks/questions_test.yaml \
  --judge --final --chunking C1 --retrieval adaptive \
  --question-source '30 test questions written by Claude in a separate chat session; 5 spot-checked against the PDFs by the user; not human-written' \
  --notes 'Stage 5 pre-registered held-out run (decision 56)'
```

### Held-out results (2026-11-05), as pre-registered (decision 56)

S run: `benchmarks/results/test_embeddinggemma_300m_C1_S_20261105T145919.json`. It recorded commit `378783b`, and its adaptive parameters match the frozen defaults. Report: `stage5_test_report_20261105T152950.json`, from `benchmarks/analysis/stage5_test_report.py`.

- **Replay of A:** it reproduced A's saved `recall_at_budget` and recall over sent evidence on all 24 answerable questions. A's sent-evidence recall equals its saved value on test as well as dev.

**Primary: S minus A, recall over sent evidence, 24 answerable: −0.019 (−0.144 to +0.106). Inconclusive; S doesn't beat A.** A scores 0.860, S 0.842.

- **3 questions changed:**
  - `fed-02`: 0 → 1 (seen).
  - `csf-03`: 1 → 0. The gold chunk was at rank 5, and the gap cutoff stopped at 1,833 tokens before reaching it.
  - `csf-04`: 1 → 0.56. It was split into parts, and the second part ("what does *its* fourth subcategory require") lost its subject.

**Secondary:**
- **Part coverage on the 4 multi-part questions:** S 1.0 / 0.5 / 0.5 / 1.0, with all parts covered on 2 of 4. A 1.0 / 0.5 / 1.0 / 1.0, all parts covered on 3 of 4. The difference is `csf-04`.
- **Table questions, gold comparison "agrees":** S 5 of 6, A 4 of 6. The only change is `bp-03` (seen).

**Guardrails:**
- **Refusals:** 6 of 6 for S. Pass.
- **False refusals:** none for S or A.
- **p50 latency:** S 31.5 s, A 32.1 s.

**Descriptive:**
- Tokens sent: S 2,274 on average, against A's 2,560. Hit@5 and MRR are identical (the same top-30 pool).
- Answerable status: S 24 answered; A 23 answered and 1 partial.
- Gold-comparison conflicts: 2 for each. Citations off gold: 3 for each. Judge off-topic flags: 2 for each.
- Faithfulness (judge): S 0.924, A 0.882.

**Seen questions, reported separately:**
- **`fed-02`:** S retrieves the table (recall 1.0) but still answers wrong (2.8%). A was partial at 2.1%. Still the flattened-header problem.
- **`fed-04`:** recall 0.64 for both, gold comparison "agrees" for both. No change.
- **`bp-03`:** **now correct under S** (97.59, against A's 94.26), with the same recall of 1.0. Retrieval didn't change, so the prompt or the evidence order did. S's prompt differs from A's (the uncovered-part notice), so this one-question gain can't be attributed to adaptive retrieval.

**Reading:**
- On held-out data, adaptive retrieval at 2,560 tokens doesn't beat top-5 on recall.
- It sends about 11% fewer tokens, keeps every guardrail, and is level on answer quality.
- Its two losses come from two of the features that held up on dev: the gap cutoff (`csf-03`) and part splitting (`csf-04`).

## Stage 6 plan (approved 2026-11-06, decisions 59–62)

**What:** OpenAI, Gemini and Anthropic as answer models, behind the existing `LLMProvider` interface, using keys the user supplies. Ollama stays the default, and the app works with no keys set.

**Why:** users can pick a stronger answer model without changing anything else. Cloud use is opt-in per knowledge base and never silent.

**Decisions:**
1. **Direct `httpx` adapters, not SDKs.** `httpx` is already installed (the Ollama client depends on it); declare it as a direct dependency. Each adapter is one small file with one request shape. Error messages are fully controlled, and mocking is easy. *Trade-off:* we maintain three request formats, so each provider's docs are checked before coding, and optional real-call tests are kept.
2. **Cloud for answering only.** Optimizer question generation and the evaluation judge stay local, so ingestion never sends a document to the cloud as a side effect and evaluation stays reproducible. **Embeddings stay local:** cloud embeddings would send every chunk off the machine and force a re-index.
3. **Choosing the model:** an optional `provider` field on the query request (`ollama`, `openai`, `gemini` or `anthropic`), defaulting to `ollama`. Model names come from settings (decision 61).
4. **Opt-in per knowledge base:** a new column, `knowledge_bases.allow_cloud`, off by default. It can be set at creation or with a new `PATCH /kbs/{id}`. A cloud query without opt-in is refused before any network call (403, clear message).
5. **Keys:**
   - Keys come only from the environment or `.env`, loaded as `SecretStr`, through **one key-loading function** that adapters get their key from (decision 60).
   - No endpoint for entering keys in this stage. `/health` reports only whether each key is configured.
   - A missing key gives a clear 400 and makes no call. Gemini's key goes in the `x-goog-api-key` header, never the URL.
6. **Structured output:** each provider's JSON-schema mode, with the same answer schema. Invalid JSON goes through the existing "generation failed" path, and citations are still built server-side.
7. **Errors:** HTTP failures become `ProviderUnavailable`, with only the provider name, status code and error type. Never headers, the request body or the key.

**Tests:**
- **Mocked contract tests** shared by the three adapters: request shape, schema, token counts, timeout, error mapping.
- **Leak tests** with a canary key. The key must never appear in logs (including `httpx` debug logging), `query_traces`, a full database text dump, exception messages, API error responses, or the printed settings.
- **Behaviour tests:** cloud refused without opt-in; the existing suite passes with no keys set; the prompt-injection test also runs through a cloud adapter.
- **Real API calls:** a `cloud` test marker, off by default, skipped without a key.

**Out of scope:** cloud embeddings, cloud judging and question generation, entering keys through the API or UI (that's Stage 7, decision 60), cost tracking, streaming, and retries beyond one timeout.

**Notes from the docs check, to re-verify before coding:**
- **OpenAI:** the Responses API (`/v1/responses`) with `text.format = {type: "json_schema", name, schema, strict: true}`. The `gpt-6-luna` model page lists structured outputs; the guide doesn't name it, so the real-call test confirms it.
- **Gemini:**
  - The structured-output guide now shows the Interactions API (`POST /v1beta/interactions`, header `Api-Revision: 2026-05-20`) with `response_format = {type: "text", mime_type: "application/json", schema}`.
  - The key goes in `x-goog-api-key`.
  - The `gemini-3.5-flash-lite` page marks structured outputs as supported. Whether `generateContent` or Interactions is the right endpoint still needs checking.
- **Anthropic:**
  - Messages API with `output_config.format`.
  - On API version `2026-10-21`, `temperature` returns a 400, so drop it for Anthropic or choose the `anthropic-version` header deliberately.
  - Haiku 5.5 thinks by default, with effort defaulting to `medium`; `low` may suit answering.

## Stage 6 results (2026-11-06)

**Built:**
- **Adapters:** `providers/cloud.py` holds one shared HTTP base and three adapters (`OpenAILLM`, `GeminiLLM`, `AnthropicLLM`) behind `LLMProvider`. `cloud_llm()` builds an adapter with the user's key or raises `MissingKey`.
- **Key loading:** `providers/keys.py` has `api_key()`, the one place keys are read. Stage 7 adds the keychain there (decision 60).
- **Settings:** three `SecretStr` key fields (decision 64) and `cloud_timeout_s` (60 s). `httpx` is now a declared dependency.
- **Opt-in:** migration `006_kb_cloud_optin.sql` adds `knowledge_bases.allow_cloud`, off by default. It can be set on `POST /kbs` or with the new `PATCH /kbs/{id}`.
- **Answering:** `answer_question(..., provider)` checks the opt-in and the key **before retrieval**, so a refused cloud request makes no call at all.
  - Refusals map to 403 (no opt-in) and 400 (no key).
  - The trace records the provider and model, never the key.
  - `QueryRequest.provider` defaults to `ollama`, and `QueryResponse` now returns `provider`.
  - `/health` reports `cloud_keys` (configured or not, per provider).
- **Schema:** `ANSWER_SCHEMA` gains `additionalProperties: false`, which OpenAI's strict mode needs.
- **Setup docs:** `.env.example` documents the keys, the model overrides and the opt-in.

**Security (CLAUDE.md rule):**
- Keys travel only in request headers.
- Error messages carry only the provider name, HTTP status and the provider's error type, never its error text (some providers echo the key).
- Exceptions are raised `from None`, so no httpx exception carrying the request headers is chained on.
- `repr()` of an adapter shows only the model.
- Test settings pin all keys to None, so a developer's real shell key can't reach a test.
- No `shortcut:` markers in security code.

**Tests:**
- **34 new, in `tests/test_cloud_providers.py`:**
  - Contract tests per provider: request shape, key only in a header, no `temperature`, schema placement, response parsing, truncation, refusals.
  - Error tests: 401 with the key echoed, 500 HTML, unreadable JSON, timeout, connection error. None may carry the key, in the message or the traceback.
  - Missing or blank key makes no call.
  - Opt-in refused before any call; opted-in answer with server-built citations and the trace's provider and model.
  - The injection document stays fenced in the cloud request; the API flow.
  - **The canary leak test** runs real HTTP to a local stand-in provider through httpx's network stack, with debug logging on for every logger. The canary must not appear in logs or log records, stdout or stderr, API responses, a database dump, the raw bytes of every file under `data/`, or the printed settings. It also checks that the canary really was sent.
- **Mutation check:** a planted leak (the provider's error text passed into the message) made the leak test fail, and the captured logs included `httpx` and `httpcore` debug output. The scratch check was removed.
- **Real calls:** `tests/test_cloud_e2e.py`, marker `cloud`, off by default, skipped without a key. Not run.
- **Full suite:** 321 passed, 10 deselected (7 `ollama`, 3 `cloud`). `ruff` is clean.

**Not verified (no real calls were made):**
- That `gpt-6-luna` accepts strict JSON-schema output.
- ~~That Gemini's `generateContent` accepts the key in `x-goog-api-key`.~~ **Verified 2026-11-06 with the user's key, 2 real calls on `gemini-3.5-flash-lite`, no quota error:**
  - `pytest -m cloud -k gemini` passed: a structured JSON answer, key in the header.
  - One question on a temporary knowledge base with `allow_cloud` gave `answered`, with a server-built citation (`note.txt, line 1`). 301 input and 61 output tokens, generation 1.2 s. The trace recorded the provider and model.
  - The key wasn't in the output or in any file the run wrote.
- That `claude-haiku-5-5` accepts `effort: "low"` together with `format`.
- Cloud answer quality and latency on the benchmark.
Running `pytest -m cloud` with your own keys checks the first three.

**Known limitations:**
- No retries; one timeout of 60 s.
- No cost tracking.
- Keys come only from the environment or `.env`; the UI and keychain come in Stage 7.
- Evaluation runs and the optimizer always use Ollama.

## Stage 7 plan (approved 2026-11-06, decisions 66–69)

**What:** a local web UI covering knowledge bases (with the cloud opt-in and deletion), uploads, questions with a provider choice and citations, API keys stored in the OS keychain, and the evaluation results. Built directly (decision 66).

**Decisions:**
1. **Stack:** React, TypeScript, Vite and Tailwind, in `frontend/`. One page with tabs; no router and no state library. Data comes from `fetch`. `node_modules/` and `frontend/dist/` are gitignored.
2. **Connection:**
   - **No CORS.** In development, Vite proxies `/api` to `127.0.0.1:8000`. For normal use, FastAPI serves the built UI from the same origin.
   - **Defence against other websites:** requests are accepted only when `Host` is `127.0.0.1` or `localhost` (blocks DNS rebinding). Changing requests (POST, PATCH, PUT, DELETE) must come from our own origin (blocks cross-site requests to localhost). Both get tests.
3. **API keys (CLAUDE.md security rule applies):**
   - **Endpoints:** write-only `PUT /keys/{provider}` and `DELETE /keys/{provider}`. `GET /keys` returns each provider's **source** (`keychain`, `env` or `not set`), never the key or any part of it (decision 68).
   - **Storage:** `keyring`, which uses the macOS Keychain. `providers/keys.api_key()` checks the keychain first, then settings; adapters don't change.
   - **Browser:** a password field, cleared after sending. Never `localStorage`, `sessionStorage`, cookies or app state after submit.
   - **Validation errors:** FastAPI's default 422 error repeats the submitted input, so the keys endpoint gets its own error handling that never echoes the key.
   - **UI:** keychain keys can be removed. A key that comes from `.env` is shown as such and edited in `.env`.
   - **Tests:** the canary leak test extends to the key endpoints, using an in-memory keyring backend: logs, responses including validation errors, DB, files. Frontend tests check that the key is absent from storage and the page after saving.
4. **Knowledge bases:** create, list and delete. Deleting gets a new backend endpoint and a confirm step in the UI (decision 67); it removes the documents, chunks, vectors and stored files. The per-knowledge-base cloud opt-in toggle. Deleting individual documents.
5. **Uploads:**
   - **Progress:** an upload progress bar via `XMLHttpRequest`, then polling `/jobs/{id}` while the document indexes.
   - **Errors:** the API's own messages appear as-is: scanned PDF ("needs OCR"), duplicate, wrong type, too large.
6. **Questions:**
   - **Provider picker:** Ollama by default. Cloud providers are offered only if a key is set, and are disabled, with an explanation, when the knowledge base hasn't opted in.
   - **Citations:** clickable, showing document, page and the cited passage. Add the passage text to the query response if it isn't there.
   - **"Insufficient evidence":** its own clear state.
7. **Evaluation view:** a read-only `GET /evaluation` serving a fixed summary built from the committed Stage 3–5 result files: A baseline, C7 vs A, C = A, and S vs A. Each comparison shows its numbers, its interval and **its verdict in plain words** (decision 69).
8. **Testing:**
   - **Frontend:** Vitest and React Testing Library, with the API mocked.
   - **Backend:** pytest for the new endpoints (keys, knowledge-base deletion, evaluation summary) and the `Host` and origin checks.
   - **End to end:** one manual check in a real browser. No browser-automation suite.
9. **Out of scope:** user accounts, streaming answers, and mobile layout polish.

## Stage 7 results (2026-11-06)

**Built:**
- **Frontend** (`frontend/`): React 19, TypeScript, Vite 8, Tailwind 4. A sidebar of knowledge bases (create, select), API keys and Evaluation; a main chat area. Answers show `[E1]` markers as numbered chips plus a source list; clicking either opens the cited passage with document, page or line, section, and "neighboring passage" for expansion chunks. "Not enough evidence" and "partial" have their own states. Per knowledge base: cloud opt-in toggle, documents panel (upload progress bar via XHR, then job polling; delete), and delete with a confirm step. API error messages are shown as-is.
- **Backend:** `LocalOnly` middleware (`Host` and origin checks, `/api` prefix); `DELETE /kbs/{id}` (documents, chunks, vectors, stored files, collection; 409 while indexing); `GET /keys`, write-only `PUT /keys/{provider}` and `DELETE /keys/{provider}` with hand-parsed bodies and fixed error messages; `api_key()` reads the keychain first; `GET /evaluation`; `passage` on citations; FastAPI serves `frontend/dist` when built. New settings: `ui_dir`, `results_dir`, `allowed_hosts`. New dependency: `keyring`.

**Tests (2026-11-06):**
- Backend: 355 passed (33 new in `tests/test_stage7_api.py`), 10 deselected. Real Ollama: 6 passed, 1 expected failure. Cloud tests not run (they cost money). `ruff check` and `ruff format --check` clean.
- Frontend: 11 passed (`npm test`): knowledge-base create and confirmed delete, citations open the passage, insufficient state, error as-is, provider picker rules, key sent once and absent from the page, storage and cookies afterwards, key removal, evaluation verdicts, upload progress and polling, upload rejection message. `npm run build` clean, `npm audit` 0 vulnerabilities.
- Canary leak test for the key endpoints (in-memory keyring): responses (including every error), headers, logs at debug, stdout, stderr, the database dump, data files and settings. All tests use the in-memory keyring and never touch the real Keychain.
- Live smoke test with curl against the real server and Ollama: UI served at `/`, foreign Host 400, cross-site POST 403, create, upload, index, cited answer in about 9 s, `GET /keys` and `GET /evaluation` correct, no key in the server log.
- Manual browser check (user, 2026-11-06). **Worked:** creating a knowledge base, uploading a PDF with the progress bar, asking a question, and the evaluation view. **Not reported:** whether citations were clicked, whether Gemini was tried in the app, and whether there were any problems. The user's message left these as unfilled placeholders, so they are not recorded as checked.

**How to run:**
1. Once: `cd frontend && npm install && npm run build`.
2. `conda activate adaptive-rag && python -m adaptive_rag` from the repo root (Ollama running).
3. Open http://127.0.0.1:8000.
For UI development: run the backend as above and `cd frontend && npm run dev`, then open http://localhost:5173.

**Known limitations:**
- Chat history lives in the page only; reloading clears it. No streaming (out of scope), so a local answer shows a waiting line for 20–40 s.
- No dark mode, and the layout targets desktop widths (mobile polish out of scope).
- Saving a key in the UI is offered only when the provider has no key; a `.env` key must be removed from `.env` first.
- The first keychain write may make macOS ask for permission.
- Deleting a knowledge base is not atomic: if interrupted, the startup check finishes deleting the documents and the row stays for a retry.

## Security finding: API key in Chroma index files (found and fixed 2026-11-06)

- **Found:** the test thought to be flaky, `test_canary_key_never_leaks_anywhere`, failed about 1 run in 20–60. Each time, the canary key was inside Chroma's HNSW file `data/chroma/<collection>/data_level0.bin`. Likely cause: the index file is written from a buffer that still holds old process memory, and in the API process that memory can contain a key. So a real key could, rarely, be written to `data/chroma/`. `data/` is gitignored, so git history is unaffected. The leak test was right; the code was wrong.
- **Fix (decision 73):** Chroma runs in a separate process (`vectorstore/process.py`, a standard-library `multiprocessing` manager), started fresh with "spawn", with every `*API_KEY*` environment variable removed while it starts. Only paths, ids, vectors and metadata are sent to it. The API starts it in its lifespan and shuts it down on exit; it also exits if the API process dies. The evaluation runner uses it too, one per Chroma directory, because `Settings` holds any `.env` keys. Still one command: `python -m adaptive_rag`.
- **Verified:** `test_canary_key_never_leaks_anywhere` now runs against the separate store process (as in normal use) with the canary also set as an environment variable; **100 of 100 consecutive runs passed** (2026-11-06, 3 providers per run). Before the fix it failed after 20 and 28 runs in two loops. The Stage 7 key-endpoint canary test also uses it and now indexes a document. New tests: the store process starts without API-key variables; the app works end to end through it and the process stops afterwards. Live check: Ctrl+C and `kill -9` of the API both stop the store process. Backend 357 passed; real Ollama 6 passed, 1 expected failure.
- **Cost:** about 1–2 s extra at startup; the full test suite went from about 9 s to about 16 s.
- **Existing data checked:** `scripts/check_key_in_data.py` (prints only provider names and file paths) found the Gemini key in **0** files under `data/` (2026-11-06). No rotation needed. Rerun it if other keys were ever used.

## Stage 8 plan (approved 2026-11-06, decisions 73–78)

1. **Key-leak fix (security finding, under Open questions):** a separate vector-store process, started and stopped by the API; no key ever enters it. 100 consecutive passes of the canary test.
2. **README:** what the app does and why it's different; quick start; Mermaid architecture diagram; held-out verdicts in plain words, each linked to its result file, questions labelled LLM-written and spot-checked; data sources and licences; the user's screenshots; link to `localdoc-rag` as the v1 prototype.
3. **Licence:** MIT `LICENSE`; check transitive dependency licences from installed metadata; note Ollama model terms.
4. **Benchmark attribution:** a "Data sources" section; no history rewrite (decision 74).
5. **CI:** GitHub Actions, Python (ruff, pytest with fakes) and Node (`npm ci`, test, build). No Ollama or keys.
6. **Clean-machine test:** fresh clone and conda env, README steps only.
7. **Secret scan** of the full history of all branches; delete the merged `stage-*` branches after the user confirms.
8. **Human-written subset** (decision 75): template and steps to the user; run only after the file arrives.
9. **GitHub:** steps for the user to create the private repo, approve the push, and later make it public.

## Stage 8 progress (2026-11-06)

- **Step 1, leak fix:** done (see "Security finding" above).
- **Steps 2–4, README, licence, attribution:** `README.md` (what and why, held-out verdicts in plain words with links to the two report files, quick start, Mermaid diagram, data sources and licences, link to `localdoc-rag` as v1). Screenshot paths `docs/screenshots/chat.png` and `docs/screenshots/evaluation.png` wait for the user's images. `LICENSE` (MIT, Pavan Rao K.); `license = "MIT"` in `pyproject.toml`, which needs setuptools 77 or newer. Licence check of the runtime dependency tree from installed metadata: 99 packages, all permissive except certifi, orjson and tqdm (MPL-2.0, file-level copyleft; fine to use unmodified under MIT). `fpdf2` (LGPL) is dev-only.
- **Step 5, CI:** `.github/workflows/ci.yml`: backend (Python 3.11, ruff, pytest) and frontend (Node 24, `npm ci`, test, build). Action versions checked 2026-11-06 (`checkout`, `setup-python`, `setup-node`, all v7). Not run on GitHub yet: there's no remote.
- **Step 6, clean-machine test:** fresh `git clone` of `stage-8-polish` into a scratch folder, new conda env `ar-clean`, README steps only: `pip install -e .`, `npm install && npm run build`, `python -m adaptive_rag`. The UI was served, a knowledge base created, a TXT indexed, and a cited answer returned; the store process stopped on shutdown. In the clone: `pytest` 357 passed, ruff clean, `npm test` 11 passed. No README fixes were needed. **Not fully clean:** the same Mac, so Ollama and its models, pip and npm caches, and conda were already present. The env and clone were deleted afterwards.
- **Step 7, secret scan (part 1):** all 21 commits on all branches. No `.env`, data, database, PDF or vector files ever committed (only `.env.example`). No key patterns (OpenAI, Anthropic, Google, GitHub, Slack, AWS, private keys). The user's Gemini key: 0 matches in history, checked by exact match without printing it. Branch deletion waits for the user.
- **Step 7, part 2 (2026-11-08):** user approved; `stage-3` to `stage-7` branches deleted with `git branch -d` (all were fully merged into `main`).
- **Step 9, GitHub (2026-11-09):** full-history secret scan clean (only the test `sk-CANARY-…` strings; the Gemini key 0 matches). `stage-8-polish` merged into `main` (`588142d`), remote `origin` added, `main` pushed (26 commits). CI run 42560709410 passed (backend 1m2s, frontend 18s). Repo is still private.
- **Step 8, human subset: deferred** (user, 2026-11-09). The template stays in the repo (`benchmarks/questions_test_human_template.yaml`); the README wording stays as is (it says a human-written subset is planned). Run it only when the user supplies the file.
- **Screenshots (2026-11-09):** `docs/screenshots/chat.png` (Demo knowledge base with the public RAGAS paper, a cited Gemini answer) and `evaluation.png` (the evaluation view). Checked for keys and personal content: none. macOS metadata stripped (comment, XMP, content-credentials chunk); pixels verified identical.
- **History rewrite and repo re-creation (2026-11-09):** see "Public-release cleanup" under Real-use findings. After the rewrite, `main` was force-pushed (`b1a0ed2`, CI passed, README images served identical to local). Because GitHub keeps force-pushed commits reachable by ID and the old CI runs link to them, the user deleted the repo. The re-created repo came up public (`private=false`), so the push was stopped; the user is recreating it as private.
- **Step 10, security pass (2026-11-09):** the user's pip-audit listed pillow 12.3.0, filelock 4.1.0 and chromadb 1.5.9. In the `adaptive-rag` env pillow was already 13.0.0 and filelock 4.2.4 (the user's audit must have been of another env or before an upgrade). pip-audit 2.10.1, run from a separate throwaway venv against the env's site-packages (118 packages), also found **oauthlib 4.0.0** (CVE-2026-49272, fixed in 4.0.1; it comes in via chromadb → kubernetes → requests-oauthlib). `pyproject.toml` now sets security floors for these transitive dependencies: `pillow>=13.0.0` (decodes images in untrusted uploaded PDFs via pdfplumber), `filelock>=4.2.1`, `oauthlib>=4.0.1`; oauthlib upgraded to 4.0.1, `pip check` clean. Tests: 388 backend, 13 frontend, build OK; one real upload through the API with Ollama embeddings: the public RAGAS PDF (18 chunks) and a generated PDF with an embedded PNG (1 chunk), both `ready`. **After:** pip-audit finds only chromadb (below); `npm audit` 0 vulnerabilities (all and `--omit=dev`). Added `SECURITY.md` (private reporting through GitHub's "Report a vulnerability"; needs private vulnerability reporting enabled in the repo's settings) and `.github/dependabot.yml` (pip, npm in `/frontend`, github-actions; weekly).
- **chromadb 1.5.9 advisories (no fixed version exists; 1.5.9 is the latest on PyPI, 2026-11-09):** CVE-2026-45829 (pre-auth code injection: a malicious model repository with `trust_remote_code` sent to the HTTP API's collections endpoint), CVE-2026-45833 (the same with UPDATE_COLLECTION permission), CVE-2026-45831 (`SimpleRBACAuthorizationProvider` ignores the tenant, database and collection a permission applies to), CVE-2026-45830 (authenticated users can read and write any tenant's collections). **Relevance: none of these paths is used.** The app embeds Chroma as `chromadb.PersistentClient` in a child process: no Chroma HTTP server, no auth or RBAC provider, no tenants, and no Chroma embedding function (vectors come from Ollama; collections are created with only an HNSW `space` setting, so nothing loads a model repository or remote code). The app talks to that process through a `multiprocessing` manager on a Unix socket in the user's temp folder, protected by a 32-byte random authkey (checked 2026-11-09), not a network port. **Would become relevant** if the project ever ran `chroma run` or used `chromadb.HttpClient`, or configured a Hugging Face or sentence-transformers embedding function. Recheck when a fixed chromadb is released (Dependabot will propose it).
- **Pushed to the new private repo (2026-11-09):** the re-created repo was confirmed private and empty (its visibility was changed from public; nothing had been pushed while it was public). `main` pushed: 30 commits, every author and committer the noreply address, head `5b23047`. CI run 42594087783 green (backend, frontend). README checked through GitHub's rendered HTML: both images (`docs/screenshots/chat.png`, `evaluation.png`) referenced, and the files GitHub serves are byte-identical to local; the Mermaid diagram renders; all 8 relative links resolve (LICENSE, manifest, both test reports, DESIGN.md, PROGRESS.md, the two images).
- **Local history cleaned (2026-11-09):** the user ran `git reflog expire --expire=now --all && git gc --prune=now`. Checked afterwards: the pre-rewrite commits (e.g. `2c3204c`, `4104727`) are gone from the local object store and no local commit carries the old Gmail address. The scratch backup bundle of the old history was deleted.

## Real-use findings (2026-11-09, reported by the user)

The user ran the app on their own documents in one knowledge base: a CA question bank (questions with source labels, no answer keys), a CA book of questions, and two ICAI study-material units (a cash-flow unit and an accounting-policies unit, each with MCQs and a separate answer-key section). These are the user's observations, not measured metrics. The documents, their titles and the user's questions are deliberately not quoted here or in the tests (decision, 2026-11-09): tests use made-up questions in the same layouts.

- **MCQ without an answer key:** when the evidence showed a multiple-choice question's options but no answer key, the model picked an option and presented it as the document's answer (two question-bank pages). **Fix:** a new rule in `SYSTEM_PROMPT` (`answering/prompts.py`): don't pick an option; say the correct option isn't given in the documents, cite where the question appears, and use status `partial`. `partial` rather than `insufficient` because `insufficient` replaces the answer with the generic message and drops the citation. Tests: `test_options_only_mcq_*` in `test_answering.py` (prompt and pipeline, fake LLM) and `test_options_without_answer_key_are_not_answered` in `test_ollama_e2e.py` (real model; uses a question the model likely knows, to test the temptation). **Not yet run against the real model:** `qwen3.5:9b` isn't installed in Ollama at the moment (`ollama list` shows only `bge-m3` and `embeddinggemma:300m`).
- **MCQ rule, round 2 (same day):** the user tested with Gemini in the app and it still picked an option. Two Gemini calls (`gemini-3.5-flash-lite`) with the real answer prompt: the old rule, asked "what is the correct answer to Q14?", **did not reproduce** (`partial`, "not given"); the strengthened rule, asked the content question instead, passed. The old rule wasn't run on that phrasing, so it's not shown that this phrasing failed before. Changes: a listed option is a possible answer, not a fact; only an explicit key ("Answer: (b)", "Ans.", a solution) counts; this holds when the question is the MCQ in other words and when the model is sure. `has_options` (3+ distinct (a)–(d) markers) repeats the rule after the evidence, like the table rule. Statute clauses "(a)(b)(c)" also trigger it; the wording is conditional, so that should be harmless, but it's unmeasured.
- **MCQ rule, round 3 (same day):** the user supplied the two failing questions (a related-party question whose option (c) is worded as a full explanation, and a question the model can answer from general knowledge) and the opposite case: a cash-flow MCQ in a study unit whose answer key is a separate list ("Answers to the Multiple Choice Questions: 1. (a) …") five pages after the question. Real Gemini tests, one call each, with passages in the same layouts (`test_cloud_e2e.py`):
  - **Round-2 prompt:** both no-key questions and a CSR question passed ("not given"); the separate-key question **failed by over-refusing** ("isn't given").
  - **Round-3 prompt** (an option's wording is never evidence however detailed; a separate answer-key list counts if it belongs to the same set of questions; with a key, answer with the keyed option and cite question and key): **all 4 passed**.
  - One run per case; model output varies, so this is a check, not a measured rate. These runs used passages in the user's documents' wording; the tests were later rewritten with made-up questions (see "Public-release cleanup") and haven't been re-run against Gemini with the new wording unless noted there.
- **Real-use results, round 4 (user, Gemini):**
  1. **Related-party question (question bank, no answer key):** Gemini still picked option (c), twice, with the round-3 prompt. The prompt rule is not enough on its own. **Fix: gate 4, a code check after generation** (`adaptive_rag/mcq.py`, applied in `answer_question` after citation validation). If the evidence has a complete (a)–(d) option set, no answer-key marker ("ANSWERS/HINTS", "Answers to the Multiple Choice Questions", "Ans. (b)", "correct answer is") and the answer hasn't already declined, an answer that names an option letter ("(c)", "option c") or reproduces an option's text is replaced with "The correct option isn't given in the documents…", status `partial`, citations kept, plus a warning. Text reproduction means runs of 5 words (whole text for 3–4-word options), counted only when most runs appear nowhere in the evidence outside the options, so an answer grounded in real standard text isn't flagged. Clause lists whose items end in ";", "; and" or "or" (statutes, the 10-K SOX certification) are not treated as options. Checks on the user's real chunks: the reworded option (c) and "(c)" are both flagged on the question-bank page; on the cash-flow unit, the keyed option with the key chunk present is not flagged, and without it is. Dev index: 0 of 377 chunks have an option set after the clause-list rule (2 before it, both the Tesla 10-K certification), so gate 4 can't change any dev answer. Limits: one-word options are caught only by letter; a paraphrase that shares no 5-word run with the option isn't caught; any key marker anywhere in the evidence turns the check off.
  2. **Separate-key question (cash-flow unit):** the question is on physical p.18, the key on p.24 under "ANSWERS/HINTS – Answers to the Multiple Choice Questions". Retrieval didn't fetch p.24, so the app said "not given". The user notes that **earlier correct answers to it cited only the question's pages, so they were guesses, not grounded answers.**
- **Answer-key linking (built and approved, 2026-11-09).** User decisions: (1) trigger whenever the evidence holds an MCQ, regardless of wording; (2) a setting, on by default in both modes, off for evaluation with `--no-answer-keys`, Stage 3–5 results stay labelled as measured without it, recorded in DESIGN.md as an approved change to baseline retrieval; (3) same document only, cross-document linking is future work; (4) a code-only count of option sets in the held-out passages.
  - **Built:** `retrieval/answer_keys.py` (called at the end of `retrieve_evidence`), setting `answer_keys`, source `answer_key` (UI: "answer key, added for the question"), gate 4 also withholds a pick that differs from the linked key. Option parsing lives in `adaptive_rag/mcq.py` so retrieval and answering share it. Eval: `--no-answer-keys`, `answer_keys` in run metadata and resume checks (old runs count as without), `_anskeys` file suffix. The evaluation summary (UI and API) says the held-out results were measured without answer-key linking and the MCQ option check.
  - **Tests** (`tests/test_answer_keys.py`, made-up documents in the study-unit layout): key after the questions in both modes, the number in the question wins, no key, key of a later set not used, key list split over chunks, budget (drops a non-MCQ chunk; skips the key when even that isn't enough), setting off, answer cites the key and a wrong option is withheld, eval resume defaults.
  - **Real index, retrieval only** (the separate-key question): baseline and adaptive both add the cash-flow unit's pp.23–24 as `answer_key`, question 1 keyed (a); the question bank has no key ("no answer key found"). Evidence 3,072 tokens of the 4,000 maximum in both modes (adaptive's 2,560 target is exceeded by the key; the hard maximum holds).
  - **One Gemini call, full app path on the real index:** `answered`, the keyed option (a), citing the question in the study unit, the same question in the question bank, and the answer key. One run.
  - **Held-out count (decision 4):** code-only, counts printed, no text: **3 option sets in 399 passages** in the C1 index (also 3 in `test_embeddinggemma_300m` and `_adaptive`, 4 in 468 in `_C7`). **Not 0, so the held-out results can't be called unaffected.** Whether those passages are real MCQs or lists the parser doesn't exclude, and whether any was sent as evidence in the held-out runs, was not checked. The dev index has 0 after the clause-list rule.
- **Real-use results with answer-key linking (user, Gemini, 2026-11-09):**
  - **Worked:** two more MCQs in the cash-flow unit, and the separate-key question: correct options with the key cited.
  - **Bug, fixed:** two questions on the accounting-policies unit were withheld as "the model's choice didn't match the answer key", although the unit's key (a grid without dots, "1 (b) 2 (a) …", p.17–18) gives the obvious answers for its Q1 and Q2. **Traces 34 and 35:** both linked the unit as **question 6, keyed (c)**. The key itself parsed correctly. The question bank's chapter on the same standard, also in the evidence, was **not** the cause: it has no key, so it linked nothing. **Root cause:** (1) the linker used only the first MCQ chunk per document (Q5's tail, Q6, the start of Q7) and ignored the chunk with Q1–Q2, which was in the evidence for trace 35; (2) it only saw questions with all four options in one chunk, so Q7, cut off at the chunk end, was invisible and Q6 was the only candidate; (3) it then matched by shared words and gate 4 trusted that guess. The traces don't store the model's own answer text, only the final status, so what Gemini answered can't be shown. **Fix:** all MCQ chunks of a document are considered, including questions cut off at a chunk edge (`visible_questions`); a target question (and so a keyed option for gate 4) is set only when the user gives the number or exactly one MCQ is in view; otherwise the key is still added and the model matches it, with no key-mismatch check. **Tests:** both cases with the evidence built as in the traces (deterministic), the full answer path with the correct options (not withheld), the dot-less key grid, and an explicit "question 2" (a wrong option is still withheld). **Real index, retrieval only (adaptive, as in the app's `.env`):** both questions now link the unit's key with no target (questions in view [6, 7] and [1, 2, 3, 6, 7]); the separate-key question still links question 1 → (a). **Still open:** for one of the two, the MCQ meant (Q2) isn't retrieved; Q7, a similar question keyed (b), is, so the answer may come from Q7. That's a retrieval issue, not a linking one.
  - **Retrieval miss, recorded, no fix now:** a question about what cash and cash equivalents don't include fetched only pp.2–3 of the cash-flow unit, not its MCQ on p.18 (expected option (d)). Same family as the index-table and exact-reference misses.
- **Answer provider memory (user request, 2026-11-09, replaces the same-day `ADAPTIVE_RAG_DEFAULT_PROVIDER` setting, which was removed):** the chat remembers the last answer model picked in the browser (`localStorage` key `lastProvider`, the provider name only, never a key; reads and writes wrapped in try/catch) and pre-selects it next time. If it isn't usable for the current knowledge base (no key, or cloud not allowed), the first usable one is selected, which is always Ollama, and the remembered choice is kept for when it's usable again. Per browser, not per user: there are no user accounts in v1. The query API's default stays `ollama`. Tests: two UI tests (remembered, fallback, storage holds only the name, junk value ignored).
- **Index tables and exact references: hybrid search tested (2026-11-09).** Private real-use set: the user's 7 questions that missed in the app (3 index-table lookups such as page ranges and question counts, 2 exact-reference lookups such as an exam paper and question number, 1 named-company question, 1 study-material MCQ), stored with their expected pages in `data/realuse/ca_questions.yaml` (gitignored, never committed; questions in the user's exact wording). The CA knowledge base had been reset in the app, so it was rebuilt from the user's four PDFs into `data/realuse/ca_index_C1` (and `_C7`); chunk boundaries match the old knowledge base exactly. Runner: `scripts/real_use_retrieval.py` (retrieval only; prints ranks, never text). New switches, **defaults unchanged**: `adaptive_keyword_query` (`"words"` | `"phrases"`: keeps a stop word or short token next to a number, so "AS 20" and "Q.5" survive, and adds adjacent words as quoted phrases) and `adaptive_fusion` (`"weighted"` | `"rrf"`: 1/(60 + vector rank) + 1/(60 + keyword rank); the top 2 keyword hits go in first, past the floor and the gap cut, not past the chunk limit or budget). Approved change to the hybrid design (user, 2026-11-09), on condition of a dev re-measure.
  - **Real-use set, C1, chunks in the top 5 / sent:** baseline 1/1, adaptive 0/0, hybrid as before 0/0, + phrases 2/2, + phrases + RRF **4/4** (the 2 exact-reference questions, the named-company question and the MCQ). No setup found 2 of the 3 index-table lookups. The user's `.env` runs adaptive + hybrid, which found 0; the MCQ miss reported earlier happened in that setup, not with baseline (baseline finds it, rank 5).
  - **Real-use set, C7 (table-aware chunks):** baseline 3/3 (one index-table lookup, rank 4; two others at rank 1), + phrases + RRF 4/3. C7 is the only setup that found an index-table answer; it costs the MCQ (rank 7). Two index-table lookups are missed everywhere.
  - **Dev (decision 49 rule: recall over the evidence sent, 56 answerable dev questions, retrieval only, C1):** S (hybrid off) 0.852; hybrid as before 0.855 (2 better, 1 worse); + phrases 0.842 (2 better, 2 worse; loses `mp-fed-01`); + phrases + RRF **0.780** (5 better, **9 worse**, mostly table and multi-part questions; +200 tokens sent). RRF fails the no-regression condition; phrases alone is about neutral. One run each.
  - **Decision:** defaults unchanged. Both switches stay available and off.
  - **One-hit variant, tried once (user, 2026-11-09), not adopted.** `adaptive_keyword_bypass` (off by default): with today's weighted ranking and word query, if the question has a phrase containing a number ("q 5", "may 2025", "as 20"), the single best keyword match for those numeric phrases goes in first, past the floor and the gap cut (not past the chunk limit or budget). Real-use set, C1: **0 in the top 5 / 1 sent** (one exact-reference question; the other picked the wrong chunk, because the dated phrase appears on many pages); baseline 1/1, hybrid as before 0/0, phrases + RRF 4/4. Dev: recall over sent evidence **0.8545, identical to hybrid as before** (no question changed; S 0.8522). No regression, but no clear help on the real-use set, so per the user's rule it is recorded and not tuned further. The switch stays, off.
- **Phrases + RRF as a personal setting (user asked, 2026-11-09): not recommended.** The condition was "no clear dev regression"; dev shows one (0.852 → 0.780, 9 questions worse, mostly table and multi-part), so no `.env` lines were given. The safer personal setting is baseline (`ADAPTIVE_RAG_RETRIEVAL=baseline`, no hybrid line), which beats the user's current adaptive + hybrid on both sets.
- **Follow-up questions, improvement #3 (built 2026-11-09).** Decisions (user): link by previous trace id on the server; rule-based detection; previous answer left out (**open option** if "explain it simply" proves weak in real use); one Gemini call for the real case. Design in DESIGN.md ("Follow-up questions"). Built: `answering/followup.py` (rules and resolver), `answer_question(..., previous_trace_id)`, prompt line for the earlier question, `QueryRequest.previous_trace_id`, `QueryResponse.searched_question`, migration 007 (trace columns), chat sends the previous turn's trace id, shows "Searched: …", **New topic** button, warnings now also shown on "Not enough evidence" answers. Tests: rule cases (8 follow-ups, 4 standalone), two-turn flow (searched text, prompt line, trace columns), chains build on the first question, a new question after a chain stands alone, a previous turn from another knowledge base is never used (standalone, warning, only that knowledge base's documents, nothing from the other chat reaches the model), unknown trace, API validation; frontend: links and shows "Searched:", New topic unlinks, another knowledge base never gets this chat's trace id. 414 backend and 15 frontend tests pass.
  - **Real case, retrieval only** (private index, the user's question asking for the solution to question 1 of the cash-flow unit, then "what is the answer"): with baseline and with adaptive + hybrid, the follow-up's search finds the question (cash-flow unit p.16–18) and links the answer key (p.23–24, question 1 → (a)); 5 of 6 evidence chunks match turn 1 in each setup (one lower-ranked chunk differs). Before this change, "what is the answer" alone retrieved nothing relevant (0 of 6 overlap).
  - **Real case, one Gemini call** (baseline; turn 1 written through the normal answer path with a canned local stand-in, because `qwen3.5:9b` isn't installed): `answered`, "the correct answer for question 1 is (a) Nil", citing the question page and the answer key; trace records the typed follow-up, the turn it follows and the base question. One run.
- **Follow-up real-use results and fixes (user, 2026-11-09).** (1) The separate-key question then "what is the answer" worked (option (a), key cited), but the reply was just "1. (a)". **Fix:** the prompt asks for letter and text ("(a) Nil"), and when the question is certain the code adds the keyed option's text from the evidence to a bare letter (`mcq.option_text`, `restate_option`); on the user's real chunk "1. (a)" becomes "1. (a) Nil". (2) "explain it simply" was linked correctly but answered `partial`: the documents have the key but no explanation. **Opt-in tutor explanation: plan proposed, not built** (see the plan in the conversation of 2026-11-09; to be recorded once decided). (3) Gemini returned 503 on one turn, and the next "what is the answer" wasn't linked: the chat linked only to the immediately preceding turn, which had failed. (The user's message didn't say whether New topic was clicked; the fix covers both cases.) **Fix:** the chat links to the last successful turn and stops at a New topic boundary (`linkableTraceId`, which also marks turns asked after New topic). **Plus one automatic retry** in the cloud adapters for timeouts and HTTP 429/500/502/503/504, after `Retry-After` (max 5 s) or 1 s; never for 400/401/403 or other client errors. Tests: retry once per temporary error and provider, `Retry-After` honoured and capped, a second failure fails cleanly (no key in the error, says "after one retry"), client errors make exactly one request; frontend: a failed turn is skipped, a New topic boundary is never crossed; restatement unit and pipeline tests, and no restatement when the question is ambiguous. Retry pauses are replaced in all tests, so the suite never sleeps.
- **Tutor explanation (built 2026-11-09).** Decisions (user): allowed for every grounded status, with a stronger label when not `answered` ("… may differ from ICAI's answer, verify before relying on it"); toggle saved per browser, off by default; 2 Gemini calls approved for the real case. Design in DESIGN.md ("Tutor explanation"). Tests (8 backend, 2 frontend): the grounded status, answer, citations and warnings are identical with the toggle off and on; a failed explanation call leaves them identical (error in its own field); no explanation call when the grounded answer fails; the explanation prompt has no evidence passages and receives the **final** grounded answer (a pick withheld by gate 4 stays withheld; "(c)…" never reaches the explanation prompt); citation markers removed, never citations; stronger label for partial and not-enough-evidence (the latter makes only the explanation call); cloud without opt-in makes no call; the trace records the request but not the text; API default off; UI: off by default, remembered, separate box with the server's label, no citation chips. 458 backend and 19 frontend tests pass.
  - **Real case, 2 Gemini calls** (private index; the separate-key question as turn 1 via a canned local stand-in, then "explain it simply" with the toggle on): grounded part `answered`, "(a) Nil", citing the question and the answer key, unchanged by the explanation; explanation in its own field with the normal label; trace recorded `requested`, 82 output tokens, 0.9 s, no text. **The explanation was weak:** it repeated the answer, said it wasn't sure, and referred to "the materials provided" (against its prompt), instead of explaining why (a gain on sale of equipment is investing, not operating). Likely cause: the prompt's "don't contradict the grounded answer" plus "say if unsure" made it over-cautious. **Not tuned** (needs measured re-runs; only 2 calls were approved). Open: revise the explanation prompt and re-check with a few approved calls.
  - **Revised (2026-11-09, 3 cases × 2 Gemini calls approved).** Check first: the explanation call **did not see the question** (only the user's wording, e.g. "explain it simply" plus the earlier question, and the grounded answer), so it explained "(a) Nil" blind. Fix: the question being explained (the MCQ stem and options) is taken from a passage the grounded answer **cited** and sent fenced as "the question"; no other evidence passages. The prompt now asks for a CA tutor's explanation: the rule or standard, the working, why each option is right or wrong, one line to remember. Tests: the numbered question is sent alone and only from a cited passage (nothing sent when nothing valid was cited); no question is guessed when two cited MCQs match equally; the gate-4 test now checks that the withheld pick isn't in the grounded answer the explanation sees, while the options appear only inside the question block; all earlier safeguards unchanged. 460 backend tests pass.
  - **Results (private index, baseline, one run each):** (1) the cash-flow separate-key question then "explain it simply": grounded `answered`, (a), key cited; explanation names the standard and principle (the gain is removed from operating profit; the sale proceeds are investing) and says why each of the four options is right or wrong; normal label. (2) A no-key related-party MCQ from the question bank: grounded stays `partial` ("not given", gate 4); explanation with the **stronger label** explains the AS 18 rule and picks the option that matches the standard's exclusion for economic dependence, with a line per option. (3) An AS 1 "NOT a major consideration" MCQ: grounded `answered` from the unit's key; explanation lists the three considerations and why the keyed option is the exception. All three received the question. **Remaining flaws, not tuned:** case 3 says what "the study material treats" as correct (against its rule); case 1 skips the "working" step (numbering jumps 1, 3, 4) though it explains the total. Quality is judged by reading, not measured.
- **Stage 5b, table and index extraction (built and measured 2026-11-09).** Decisions (user): text-line parsers + SQLite + exact lookup, no new dependency; opt-in in both modes, off by default; generic + ICAI patterns in one module, tested not to harm generic documents; backfill from stored text; the ~12 new dev questions drafted in a **separate fresh session** that hasn't seen the parser or any results, reviewed by the user, before any evaluation; printed counts only. Design in DESIGN.md ("Exact lookups").
  - **Diagnosis (private CA PDFs, samples not committed):** the loader keeps index rows and question headers intact as lines, but merges columns ("12 40 - 44" means 12 questions, pages 40–44 only via a header printed once); C1 packs ~35 index rows into two chunks, the header only in the first; one row can't stand out for search; "Q.n" appears 1,300+ times per book and the chapter comes from a heading pages away. pdfplumber 0.11.10's table finder merges all columns into one cell on the index pages (shaded rows, no vertical rules) and fragments words in text mode. PyMuPDF 2.1 is AGPL-3.0 and now needs onnxruntime; Camelot 2.0 is MIT but brings pandas.
  - **Built:** parsers, migration 008, parsing at upload, backfill command, lookup step, `--lookup` evaluation flag and metadata, runner setups `base+lookup` and `adapt+lookup`, UI label "found by exact reference". Parsed: BQ 34 contents rows (all with printed counts) and 1,622 references; CQ 40 and 1,067; dev: Tesla 23 rows and 32 references (Items, Exhibits), NIST 23 and 26 (Tables, Figures), Fed 109 figure and table captions, RAGAS 5 tables. Tests: 6 parser tests (ICAI-style and 10-K-style made-up layouts; index lines aren't contents rows; financial rows, mid-sentence mentions, lists of tables and contents-page entries don't become captions) and 13 lookup tests through real ingest on made-up PDFs (off by default changes nothing; exact reference first with the right page and chapter; contents row with header and printed count; listing; ambiguous reference skipped; generic documents and questions unchanged; another knowledge base never searched; budget; citation page and gate; follow-up keeps the reference; backfill; eval resume default); 1 UI test. 479 backend and 20 frontend tests pass.
  - **New dev lookup questions:** `benchmarks/questions_dev_lookup.yaml`, 12 questions (9 factual, 1 table, 2 near-miss; 10 answerable) written in a separate fresh session from the dev PDFs only, reviewed and approved by the user as written (source "claude-separate-session, user-reviewed"). **Frozen 2026-11-09, SHA-256 `1f5f9d4acaaab50db8f0a89b34b1698889a6aeae2c2206fc6e1a38e7bc1eb256`**; the validator passes and all quotes are on their stated pages.
  - **Measurements (2026-11-09, retrieval only, C1, recall over the evidence sent; results in `benchmarks/results/stage5b/`, 16 runs, lookup off vs on, settings from flags only):**

    | Set | Mode | n | Off | On | Better / worse |
    |---|---|---|---|---|---|
    | Main dev | baseline | 29 | 0.862 | 0.862 | 0 / 0 |
    | Main dev | adaptive | 29 | 0.862 | 0.862 | 0 / 0 |
    | Dev tables | baseline | 15 | 0.800 | 0.800 | 0 / 0 |
    | Dev tables | adaptive | 15 | 0.867 | 0.867 | 0 / 0 |
    | Dev multi-part | baseline | 12 | 0.810 | 0.810 | 0 / 0 |
    | Dev multi-part | adaptive | 12 | 0.810 | 0.810 | 0 / 0 |
    | **New lookup questions** | baseline | 10 | 0.500 | **0.600** | 1 / 0 |
    | **New lookup questions** | adaptive | 10 | 0.300 | **0.400** | 1 / 0 |

    No regressions anywhere: every main, table and multi-part question is unchanged (lookup matched nothing on them). The one gain is an Item reference in the 10-K (lk-05). **Misses, diagnosed but not fixed** (fixing them now would tune on these questions): two "Table N" references were skipped as ambiguous (8 and 4 matches across the four documents) although the question names the document, because reference matching doesn't use the document hint that contents matching uses; a contents question about a one-word title ("Cybersecurity") scored below the 2-word threshold; an "exhibit 21.1" question matched a later mention instead of the exhibit-index row, which doesn't repeat the word "Exhibit". Tokens sent rise only on the lookup questions (+171 baseline).
  - **The user's 7 private CA questions (sent to the model, off → on):** C1 baseline 1 → **5**, C1 adaptive 0 → **4**, C7 baseline 3 → **6**, C7 adaptive 3 → **6**. Found by lookup: two index-page lookups (a chapter's page range; a chapter's question count and pages), one exact exam-paper reference, and one printed topic count; with C7 also the two that C7 search already found. Still missed: the practice-question source on C1 (the question names no label the parser stores), the named-company question on C1, and the cash-equivalents MCQ on C7 (rank 7, as before).
  - **Extraction caveat from the question session (checked, no change):** pdfplumber's default `extract_text()` glues words on NIST and RAGAS pages (603 and 324 glued words of 20+ letters); with `x_tolerance=1`, 6 and 0. The app's loader already uses `X_TOLERANCE = 1`, and its stored text for those documents has 0 glued words.
  - **Decision (user, 2026-11-09): lookup on by default in both modes.** `structured_lookup = True`; `ADAPTIVE_RAG_STRUCTURED_LOOKUP=false` turns it off; the evaluation CLI follows the app default and `--no-lookup` turns it off (recorded in run metadata; runs saved before 2026-11-09 count as without). The real-use runner's non-lookup setups now turn it off explicitly. The adoption rule was met (beats the current setup on the new dev lookup questions, no regressions on the main dev set), but the dev gain is one question; most of the evidence is the 7 private CA questions. README, DESIGN.md updated with the measured numbers.
  - **Known limitations, left for later (user decision):** (1) references aren't narrowed by the document the question names, so "Table N in the X document" is skipped as ambiguous when several documents have a Table N (lk-07, lk-08); (2) a contents row with a one-word title can't reach the 2-word match threshold (lk-01); (3) an exhibit-index row that doesn't repeat the word "Exhibit" isn't stored as that exhibit's label, so a later mention is matched instead (lk-06). Fixing them needs a fresh set of lookup questions to measure, since the current set has now been used for diagnosis.
  - **Real-app re-test with lookup on (user, Gemini, CA knowledge base, 2026-11-09): 4 of 4 correct.** A chapter's page range from the Book of Questions index; a chapter's question count and pages (citing the BQ index); the mixed-topic case count and pages (from the CQ book itself); and an exam-paper question's text in chapter 1 (citing the question's pages). Traces confirm each was found by lookup (3 contents rows, 1 reference).
  - **Gap 1, short phrasings don't trigger lookup:** "<chapter name> in the Book of Questions" and "<index topic>" alone got `partial` answers citing content pages; the traces show no lookup match, because those phrasings have no lookup wording ("which pages", "how many"). **Plan proposed, not built:** let a short question that is essentially an index title trigger the contents lookup; measure on dev and on the private set before adopting.
  - **Gap 2, a citation chip with no inline marker:** citations are built from the "[E1]" markers in the answer text plus the model's `cited_ids` list (`answer.py`, `_resolve`); the UI places inline chips only where a marker is in the text. In the mixed-topic answer the model listed the passage in `cited_ids` but wrote no marker in the sentence, so the citation was valid and listed but had no inline position. (Traces don't store answer text, so this is the code path, not a replayed answer.) Fix proposed, not built: when an answer cites passages only through `cited_ids`, the server appends their markers at the end of the answer.
  - **Built after the re-test (2026-11-09; user decisions: whole-title match only; a fresh session writes the questions; fix the inline marker):**
    - **Inline markers:** when an answer cites passages only through `cited_ids`, the server appends their markers at the end of the answer (`_resolve`), so every citation has a place in the text. Answers that already have markers are unchanged. Test: `test_citations_given_only_in_cited_ids_get_inline_markers`.
    - **Bare index titles, opt-in (`lookup_bare_titles`, off by default):** see DESIGN.md ("Exact lookups", item 5). Tests (9): off by default; a whole title, with or without its document's name, triggers it; a question word, part of a title, words that don't name the document, or a long question don't; with two books carrying the same title, naming one picks it and naming neither returns both. Evaluation flag `--bare-titles`; real-use runner setup `base+bare`. 489 backend tests pass.
    - **Questions:** `benchmarks/questions_dev_short_lookup.yaml`, 12 (8 short title, 4 short topical), written in a separate fresh session from its saved prompt (`data/short_lookup_questions_prompt.md`), reviewed and approved by the user as written; sources set to "claude-separate-session, user-reviewed". **Frozen 2026-11-09, SHA-256 `7d29947c2c5ee6fc3b326837d532180cb511c338ee6a07f84bc68f7115e43dba`.** The user's two short CA phrasings were added to the private set (now 9 questions).
    - **Measurements (2026-11-09, retrieval only, C1, lookup on, rule off → on; results in `benchmarks/results/stage5b_bare/`, 20 runs):**

      | Set | Baseline | Adaptive | Better / worse | Rule fired |
      |---|---|---|---|---|
      | Short lookup (12) | 0.417 → **0.674** | 0.417 → **0.674** | 4 / 0 | 5 (all on title questions) |
      | Main dev (29) | 0.862 → 0.862 | 0.862 → 0.862 | 0 / 0 | 0 |
      | Dev tables (15) | 0.800 → 0.800 | 0.867 → 0.867 | 0 / 0 | 0 |
      | Dev multi-part (12) | 0.810 → 0.810 | 0.810 → 0.810 | 0 / 0 | 0 |
      | Frozen lookup (10) | 0.600 → 0.600 | 0.400 → 0.400 | 0 / 0 | 0 |

      **No false triggers:** the rule fired on none of the 4 topical questions (sl-09 to sl-12) in either mode, and on no question of the other sets. It fired on 5 of 8 title questions; 4 gained (three 10-K Items, both modes), 1 fired but missed (below). Tokens sent rise only on the short-lookup set (+170).
    - **Private CA set (sent to the model):** C1 baseline 1, + lookup 5, + lookup + rule **7**; adaptive + lookup 4, + rule **6**; C7: 3 / 6 / **8**, adaptive 6 / **8**. The rule found both short phrasings in every setup and changed nothing else.
    - **Title misses, diagnosed, not fixed:** (1) **A bug in the default lookup, not a phrasing gap:** for sl-04 the rule matched the right contents row, but the row starts 2 characters before the end of a chunk, and `_chunk_at` picks the first chunk containing the row's *start*, so it added a chunk holding only "1." of the line while the full line is in the next (overlapping) chunk. It affects any contents row or reference cut by a chunk boundary, with the rule on or off. (2) sl-05: the contents line "Appendix B: How AI Risks …" isn't parsed (a colon after the label), and the title starts with "How", a question word for the rule. (3) sl-07, sl-08: the Fed report's contents ("Box N. … . . . . 31") isn't parsed at all (0 rows): "Box" labels and spaced dot leaders.
    - **Decision (user, 2026-11-09): the rule is on by default.** `lookup_bare_titles = True`; `ADAPTIVE_RAG_LOOKUP_BARE_TITLES=false` turns it off; evaluation runs use `--no-bare-titles` (runs saved before count as without). The real-use runner's `base+lookup` and `adapt+lookup` setups now turn the rule off explicitly. README and DESIGN.md updated with the measured numbers.
    - **Known limitations added (user decision, left for later):** a contents label followed by a colon ("Appendix B: …") isn't parsed; the Fed report's contents format ("Box N." labels, spaced dot leaders) isn't parsed at all; a title that starts with a question word can't trigger the rule.
    - **Chunk-boundary bug, fixed (2026-11-09, separate commit):** `_chunk_at` now takes the matched line's start and end and returns the first chunk holding the whole line; only if no chunk holds it whole does it fall back to the chunk where the line starts. Used for references, contents rows and the printed question index. Test `test_a_row_cut_by_a_chunk_boundary_comes_from_the_chunk_holding_it_whole` (made-up document with hand-made overlapping chunks, the row starting 2 characters before the first chunk's end); checked to fail on the unfixed code (it picked the chunk with only the line's start) and pass on the fix. **Checks, regression only (no tuning):** the private CA set is unchanged in every setup (C1 baseline + lookup + rule 7 of 9 sent; C7 8 of 9); one run of the main dev set with the current defaults, both modes, is identical to the run before the fix (0.862, no question changed in recall or tokens sent; `benchmarks/results/stage5b_fix/`). The other dev sets weren't re-scored, as decided.
  - **Backfill of the user's app data (2026-11-09):** `python -m adaptive_rag.backfill_structure` parsed all 6 ready documents (the Demo knowledge base and the user's re-created CA knowledge base with 5 documents: two question books with 34 and 40 contents rows and 1,622 and 1,067 references, and three study-material units with 0–5 caption labels each). No re-upload or re-embedding.
- **Side finding: `.env` leaked into two dev evaluation runs.** The Stage 5 dev table-prompt runs (`dev_embeddinggemma_300m_C1_S_20261105T114552`, `..._tblprompt_20261105T120303`) record `hybrid: True` in their metadata, apparently from the user's `.env` (`ADAPTIVE_RAG_ADAPTIVE_HYBRID=true`), although decision 55 set hybrid off for S. The held-out S run (`test_embeddinggemma_300m_C1_S_20261105T145919`) recorded `hybrid: False`, so the published held-out results are unaffected. The table-prompt comparison (decision 47) was made between two runs with the same hybrid setting, so it stays internally consistent, but it was not measured on S as defined. **Fixed (2026-11-09):** `config.code_default_settings()` builds settings from code defaults plus explicit values only, ignoring both the `.env` file and `ADAPTIVE_RAG_*` environment variables. The evaluation CLI (`_settings`), `benchmarks/analysis/optimize_dev.py` and `scripts/real_use_retrieval.py` use it; evaluation runs set retrieval switches with flags (`--hybrid`, `--keyword-query`, `--fusion`, `--keyword-bypass`), recorded in the run metadata. Test: `test_evaluation_settings_ignore_a_personal_env` (a `.env` and environment variables are set; normal `Settings()` picks them up, evaluation settings don't). Checked in practice: the one-hit dev runs were started with `ADAPTIVE_RAG_ADAPTIVE_HYBRID=true` in the shell, and the S run still recorded `hybrid: False`.
- **Effect on reported results:** the README's held-out results were measured with the earlier prompt. The new rule should only change answers on MCQ-style evidence, which the benchmark doesn't target, but that is an expectation, not a measurement. Don't rerun the held-out set for this (see Next steps).
- **Public-release cleanup (user decisions, 2026-11-09):** (1) git history rewritten so every commit uses the GitHub noreply address `315021662+Pavan-1232@users.noreply.github.com`, also set as `user.email` for this repo; (2) text copied from the user's CA/ICAI documents (and the user's questions) replaced with made-up questions and answer keys in the same layouts in tests, and described generically in this file. The five commits that contained copied text (the MCQ rule through the AS 1 linking fix) were squashed into one with the cleaned content, so no commit holds the original text.

## Workspace state

- **Branches:** `main` (Stages 2–8, history rewritten 2026-11-09, pushed to `origin`, now public) and `stage-8-polish` (merged, local only). `user.email` for this repo is the GitHub noreply address. Commit only when the user asks.
- **Frontend:** `frontend/node_modules/` and `frontend/dist/` are gitignored; `package-lock.json` is committed with the rest.
- **Keys:** the user's Gemini key is in the gitignored `.env`. Never print, log or commit it.
- **Environment:** conda env `adaptive-rag` (Python 3.11.18), project installed in editable mode. Ollama 0.40.14. As of 2026-11-09, `qwen3.5:9b` (the default `llm_model`) is not installed; pull it before using the app or running `pytest -m ollama`.
- **Data:** `data/eval/dev_embeddinggemma_300m_C1/` now has migration 005 (FTS5 index filled from existing chunks). The held-out indexes under `data/eval/test_*` are untouched. Everything under `data/` is gitignored.
- **Config defaults:** `retrieval = "baseline"`, `table_prompt = False`. The `adaptive_*` settings and `evidence_target_tokens` (2560) are finalist S (decision 55), with `adaptive_hybrid = False`. Optional switches can be set to None from the environment with `null`.
- **Test set:** not opened. Only IDs, counts and hashes used.
- No process running.

## Next steps

1. **Stage 8:** the repo is public. Check that private vulnerability reporting is enabled in the repo's Settings → Security (SECURITY.md relies on it) and "Keep my email addresses private" in GitHub's email settings. The human-written subset (decision 75) is deferred.
2. **Real-use follow-ups:** run `pytest -m ollama` once `qwen3.5:9b` is back, to check the MCQ rule with the real model. Decide whether to check, counts only, if the 3 held-out option sets were ever sent as evidence (see "Held-out count"). Investigate the index-table and exact-reference failures.
3. **Optional, any time:** run `pytest -m cloud -k openai` or `-k anthropic` with the user's own keys, to verify those two adapters for real.
4. **Future work, top item: Stage 5b (table extraction)** (decision 58).
   Also future work (user, 2026-11-09): **No-Ollama mode — cloud embeddings so the app works with only a cloud key. Needs re-indexing per knowledge base and sends whole documents to the provider at upload, so it must be opt-in.** And **cross-document answer-key linking**: a question bank's source label (e.g. "Source: Study Unit 4, Practice Q.7") to the ICAI unit PDF in the same knowledge base.
5. **Don't rerun the held-out test set** until the next release.

## Open questions

- Registry matching: should "has tables" mean any detected table, or table share above about 2%? Deferred: no optimizer tuning in Stage 4.
