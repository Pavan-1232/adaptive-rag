# Adaptive RAG: Progress

**Last updated:** 2026-10-30
**Current state:** Stage 2 complete and committed. Do not start Stage 3 until the user approves.

The approved architecture is in [DESIGN.md](DESIGN.md).

## Stage status

| Stage | Name | Status |
|---|---|---|
| 1 | Design | Complete; approved 2026-10-30 |
| 2 | Baseline backend | Complete 2026-10-30; awaiting approval |
| 3 | Evaluation harness | Not started |
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

## Workspace state

- Git is initialized with `.gitignore`. Stage 2 is committed on `main`. Commit only when the user asks.
- The conda env `adaptive-rag` exists (Python 3.11.18) with the project installed in editable mode.
- Ollama models installed: `embeddinggemma:300m`, `qwen3.5:9b`, `gemma4:e4b`. `qwen3.5:4b` (the fallback) is not installed.

## Next steps (Stage 3, after approval)

Build the evaluation harness: span-overlap metrics, question generator with bias filters, runner, report, and a human benchmark of about 30 questions. Test `gemma4:e4b` alone before relying on it as judge. Compare embedding models with measurements.

## Open questions

- Which specific public documents go in the benchmark, and how are they split between dev and test? To settle in Stage 3.
