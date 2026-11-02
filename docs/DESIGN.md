# Adaptive RAG: Design

**Status:** Approved at the end of Stage 1 (2026-10-30). Keep this file current when a design decision changes.

Numeric settings marked "starting value" are untested defaults to calibrate. They are not measurements. The Stage 2 smoke test measured speed and memory (see `PROGRESS.md`). Retrieval quality has not been measured yet.

## 1. Key design principles

1. **Canonical text with offsets.** Every document is extracted to one stored text, plus page and section maps. Every chunk is a character range in that text. Citations, neighbor merging, and evaluation evidence all use those ranges.
2. **Recall@budget is the primary metric.** Hit rate, recall@k, and MRR favour large chunks, so selection compares evidence covered within a fixed token budget.
3. **Evidence is stored as character spans, not chunk IDs.** One question set can then score every chunking candidate fairly.
4. **The server builds citations.** The LLM returns evidence IDs (`E1`, `E2`). Code looks up the document and locator, so the model cannot invent a page number.
5. **Public test benchmark.** Personal documents can't be committed, and results must be reproducible.
6. **Honest controls.** Compare against a fixed baseline and a single best global config. "A simple config was enough" is an acceptable result.

## 2. Feasibility

| Level | Items |
|---|---|
| Straightforward | FastAPI, knowledge bases, TXT/DOCX loading, fixed and recursive chunking, baseline retrieval, metrics, BYOK adapters |
| Hard | Headings from messy PDFs; choosing between candidates with few questions; thresholds that don't carry across embedding models |
| Risky | Detecting insufficient evidence from similarity scores; biased self-written questions; slow local question generation; adaptive retrieval may not beat the baseline |
| Wait | OCR, XLSX/PPTX/HTML, reranking, multi-hop query decomposition, document summaries, auth, streaming |

## 3. Stack

| Area | Pick | Why | Alternative | Trade-off |
|---|---|---|---|---|
| Python env | New conda env `adaptive-rag`, Python 3.11 | Clean dependencies; `rag-env` stays untouched | Reuse `rag-env` | Reuse risks breaking other work |
| LLM | `qwen3.5:9b` (6.6 GB) | Installed, Apache 2.0, leaves more free memory | `gemma4:e4b` (9.6 GB) | Gemma may be as good but leaves little room on 16 GB |
| Fallback LLM | `qwen3.5:4b` (3.3 GB) | For memory pressure; needs downloading | `gemma4:e2b` | Probably lower answer quality |
| Evaluation judge | `gemma4:e4b`, provisional; probe results and proposed changes are in `PROGRESS.md` | Different model from the answer LLM | Same LLM | Same model would mark its own work; at 9.6 GB, memory is the concern. Fallback: `qwen3.5:4b` or a smaller Gemma |
| Embeddings | `embeddinggemma:300m` (622 MB, 768 dimensions) | Installed, small, batch support via `/api/embed` | `bge-m3` | Compare with measurements in Stage 3 |
| PDF | `pdfplumber` | Permissive licence, exposes font data for headings | PyMuPDF | PyMuPDF is faster, but AGPL conflicts with possible commercial use |
| DOCX | `python-docx` | Reads heading styles | `docx2txt` | Plain text only, loses structure |
| Vectors | ChromaDB `PersistentClient` | Project default | LanceDB | No reason to switch |
| Metadata | Standard-library `sqlite3`, plain SQL | Visible logic, no extra dependency | SQLModel | Slightly more boilerplate |
| Orchestration | Plain Python, no LangChain | Chunkers need exact character offsets | LangChain splitters | More code, but core logic stays visible |
| Background work | FastAPI `BackgroundTasks`, job status in SQLite, one worker | No queue needed | Celery/RQ | Jobs die on restart, so they must be resumable |
| Token counting | `tiktoken` plus a safety margin | Provider-neutral estimate | Characters / 4 | Estimate only; actual usage is logged from Ollama |

### Settings that prevent silent bugs

- Ollama's default context is 4096 tokens. Always set `num_ctx` explicitly (starting value 8192).
- Thinking is on by default for `qwen3.5:9b`. Always pass `think=False` for generation. In the smoke test, thinking mode produced no usable output within a 1024-token limit.
- EmbeddingGemma expects task prompts, which the provider must add:
  - Query: `task: search result | query: {content}`
  - Document: `title: {title or "none"} | text: {content}`
- EmbeddingGemma has a 2K context, so chunk sizes stay at or below 1024 tokens. By default Ollama silently truncates longer inputs (measured: 3,000 words accepted, 2,048 tokens processed), so oversized chunks must be rejected or split, never embedded as they are.
- Create Chroma collections with `configuration={"hnsw": {"space": "cosine"}}`. Treat `space` as fixed at creation.
- Pass precomputed vectors to Chroma rather than using a Chroma embedding function, to keep control of the prompts.
- Avoid Ollama `:cloud` tags, because they send content off the machine.
- Verify library APIs against current documentation when implementing.

## 4. Architecture

```
INGEST
Upload → Validate (type, size, magic bytes) → Hash and duplicate/version check
→ Extract to CANONICAL TEXT + page map + section map (with char offsets)
→ Extraction quality gate (empty/scanned → clear failure, "needs OCR")
→ Profile document → Registry lookup
     ├─ strong match → reuse config
     ├─ borderline match → cheap re-test
     └─ no match → full optimization on sampled sections
→ Chunk → Embed → SQLite (source of truth) + ChromaDB (vectors) → Mark doc "ready"

QUERY
Question → Rule-based query analysis → Embed → Fetch candidate pool
→ Dynamic cutoff → Evidence gate (too weak → say so, no LLM call)
→ Dedupe/diversity → Neighbor expansion → Token budget
→ LLM answer using evidence IDs (E1, E2...) → Validate IDs and build citations in code
→ Response with status → Trace log (scores, tokens, time per step)
```

### Citation locators

| Format | Locator |
|---|---|
| PDF | Physical page, plus the printed page label if available |
| DOCX | Section heading and paragraph range (no reliable page numbers) |
| TXT | Section (if detected) and line range |

Chunks store `locator_start` and `locator_end`. The document's `locator_kind` says whether those are pages, paragraphs, or lines. Printed page labels are not implemented yet, so PDF citations use physical page numbers.

### PDF extraction

Testing on real PDFs in Stage 2 showed that pdfplumber's defaults glue words together and interleave columns. The loader therefore:

- Uses `x_tolerance=1` to keep words separate.
- Finds two-column pages from a vertical gutter that almost no word crosses, and reads any full-width top band, then the left column, then the right.
- Drops rotated text, such as arXiv's margin stamp.
- Removes running headers and footers, and repairs words hyphenated across lines.
- Detects headings from font size, or from a bold font at body size or larger.

## 5. Chunking optimization

### Candidates (maximum 6)

| ID | Strategy | Size / overlap (tokens) | Condition |
|---|---|---|---|
| C1 | Fixed | 512 / 50 | Always; the control |
| C2 | Recursive | 256 / 25 | Always |
| C3 | Recursive | 512 / 50 | Always |
| C4 | Recursive | 1024 / 100 | Always |
| C5 | Structure-aware | Up to 512 | Only if reliable headings are found |
| C6 | Semantic (embedding breakpoints) | Up to 512 | Skipped when cost caps are reached |

Semantic chunking is tested, not assumed better. A Vectara study found its extra cost wasn't backed by consistent gains.

### Question generation

1. Sample sections from the canonical text, spread across the document, without using chunk boundaries.
2. The LLM returns a question and an exact supporting quote, using a Pydantic schema with Ollama structured output.
3. Code locates the quote and stores its character span. If it can't be found, the question is dropped.
4. A hit means a chunk covers at least 50% of the evidence span (starting value).

### Bias controls

| Bias | Control |
|---|---|
| Questions copy passage wording, flattering embeddings | Ask for paraphrases; reject high word overlap with the quote |
| Sampling favours the start of the document | Stratify across sections |
| Questions are too easy | Fixed mix of factual, conceptual, and multi-sentence types |
| Questions are shaped by a chunking strategy | Generate them before any chunking happens |
| Winner's score is inflated by selection | Score the winner on separate confirmation questions |
| The model marks its own work | `gemma4:e4b` as judge, plus the human benchmark |

### Scoring

| Metric | Role |
|---|---|
| Recall@budget: share of evidence covered within 2000 retrieved tokens (starting value) | Primary |
| Hit rate@5, recall@5, MRR | Reported; they favour larger chunks |
| Processing time, chunk count, storage | Tie-breakers |

### Selection rule

1. Exclude candidates that fail checks, such as chunks over the embedding limit.
2. Rank by recall@budget on the selection questions.
3. Compute a paired bootstrap 95% confidence interval for each candidate against the leader.
4. Treat any candidate whose interval includes zero as tied.
5. Pick the simplest tied candidate: fixed → recursive → structure-aware → semantic. Break remaining ties by smallest storage.
6. Report the winner's score on the confirmation questions.

Many documents will tie and get a simple config. The system must not claim a difference it can't detect.

### Cost controls (starting values, calibrate in Stage 4)

- At most 6 candidates and 40 questions per document (30 selection, 10 confirmation).
- The smoke test measured a median of 5.6 s per question with `think=False`, so the 40-question limit stays.
- Sample about 25% of tokens, capped at 30,000. Short documents are evaluated in full.
- A time budget per document. When it runs out, stop and keep the best result so far.
- Evaluate with in-memory NumPy search and cached embeddings, so Chroma isn't filled with temporary data.

Sampled scores run high because there are fewer distracting chunks. They are valid only for comparing candidates, not as a measure of final quality.

### Configuration registry

This is configuration caching using rule-based profile matching. It is not ML.

| Group | Fields |
|---|---|
| Identity | `config_id`, strategy, size, overlap, chunker code version |
| Context | Embedding model and digest, embedding prompt version, extractor version |
| Profile | Format, pages, tokens, heading density, mean section length, table share, characters per page, language |
| Evidence | Scores, confidence intervals, question count, runtime, source document |
| Usage | Times reused, last re-test result |

| Situation | Action |
|---|---|
| Same format, profile within tolerance, same embedding model | Reuse with no test |
| Same format, profile borderline | Cheap re-test: 10 questions, cached config vs C1 |
| Cheap re-test loses to C1 | Full optimization for that document |
| No match, or very different structure | Full optimization |
| New version of a document | Re-profile, then re-chunk that document only |
| Config changes for a document | Re-index that document only |
| Chunker or extractor version changes | Re-index affected documents; mark registry entries stale |
| Embedding model, dimensions, or prompt format changes | Full knowledge base re-index into a new collection, then switch over |

Stage 4 measures the regret of reuse: quality lost by reusing a config instead of running full optimization.

## 6. Adaptive retrieval

| Step | Design | Evaluated by | Version |
|---|---|---|---|
| Baseline | Fixed top-5 by cosine similarity | Reference for everything else | v1 |
| Query type | Rules only: factual, comparative, broad | Accuracy on labelled dev questions | v1 |
| Dynamic depth | Fetch 30, then apply the cutoff rules below | Recall@budget, tokens used | v1 |
| Evidence check | Score gate, LLM status, citation validation | False-answer and false-refusal rates | v1 |
| Neighbors | Algorithm below | Recall gain vs extra tokens | v1 |
| Dedupe | Merge overlapping spans; drop near-identical chunks | Duplicate tokens removed | v1 |
| Diversity | Per-document cap for comparative and broad questions only | Sources covered, recall | v1 |
| Token budget | Greedy fill with hard limits | Never exceeded (tested) | v1 |
| Keyword + vector search (SQLite FTS5) | Hybrid scoring | Comparison against vector-only | v1.1, top candidate |
| Cross-encoder reranking | Heavy dependency on 16 GB | Compare later | Later |
| Query rewriting, multi-hop | Extra LLM calls and latency | Compare later | Later |
| Per-entity coverage check | Harder comparative logic | Compare later | Later |

### Dynamic depth

| Type | Min–max chunks (starting values) |
|---|---|
| Factual | 3–5 |
| Comparative | 5–10 |
| Broad | 8–15 |

Keep chunks in score order and stop at the first of:

- The chunk's score falls below the floor.
- The score falls below `top_score − delta`.
- The largest score gap in the range is reached.
- The type's maximum is reached.

The floor and delta are tuned on dev questions and stored per embedding model. The floor is set in Stage 3 (`score_floors` in `config.py`); delta is tuned in Stage 5.

### Evidence check

1. Before the LLM: if the top score is below the floor, return `insufficient` without calling the model. This catches only clear cases, since a high score doesn't prove the passage answers the question.
2. LLM status: the model returns `answered`, `partial`, or `insufficient`.
3. After the LLM: an answer with unknown or missing evidence IDs can't be returned as `answered`.

### Neighbor expansion

```python
reserve = 30% of evidence budget for neighbors
for hit in direct_hits_by_score:
    if hit.score < expand_threshold: continue
    for neighbor in (hit.index - 1, hit.index + 1):      # same document only
        skip if already selected
        skip if it crosses into a different section
        skip if it would exceed the reserve
        add it, marked source="expansion", parent=hit.chunk_id
merge overlapping/adjacent ranges in each document into one evidence block
order: blocks by best direct score, text inside a block in document order
```

The merged block records which chunks were direct hits and which came from expansion, and so does the trace log.

### Token budget (starting values, `num_ctx` = 8192)

| Slice | Tokens |
|---|---|
| System prompt and question | ~700 |
| Reserved for answer | 1024 |
| Unallocated margin | At least ~2470 |
| Evidence | Default target 2500; hard maximum 4000 |

Direct hits fill first, then neighbors. Whole blocks are dropped rather than cut mid-sentence.

The 2500 target comes from measured latency: warm answers took 19–22 s at about 2,600 prompt tokens and about 33 s at about 3,900. Stage 5 tests whether it limits adaptive retrieval. The fixed top-5 baseline uses the 4000 maximum so that it isn't silently reduced below five 512-token chunks.

## 7. Storage

| Data | SQLite | ChromaDB |
|---|---|---|
| Knowledge bases, documents, versions, hashes, job status | Yes | |
| Canonical text, page and section maps | Yes | |
| Chunk text, offsets, index, pages, heading, config ID | Yes | |
| Vectors | | Yes |
| Filter fields: `document_id`, `chunk_id`, `chunk_index`, `locator_start`, `locator_end`, `config_id` | Master copy | Copy |
| Registry, questions, evaluation runs, traces | Yes | |

Original files go in `data/files/`, which is gitignored.

- **Source of truth:** SQLite. Chroma can be rebuilt from it by re-embedding.
- **Separation:** one Chroma collection per knowledge base and embedding model, such as `kb_12__embeddinggemma_85462619`. A filter bug can't leak results between knowledge bases, and re-indexing can run alongside the live collection.
- **Memory:** the LLM is unloaded after ingestion jobs, because system memory reached 15.4 GB of 17.2 GB in the smoke test.
- **Consistency:** the stores share no transaction. A document goes `indexing` → write to Chroma → `ready`, and only `ready` documents are searched. A startup check repairs anything half-done.
- **Duplicates:** the same hash in the same knowledge base returns the existing document. A changed file with the same name becomes a new version, and the old one is removed only after the new one is ready.

## 8. Providers and secrets

```python
class EmbeddingProvider(Protocol):
    id: str
    model: str
    prompt_version: str
    def version(self) -> str: ...
    def dimensions(self) -> int: ...
    def embed_documents(self, texts: list[str], titles: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class LLMProvider(Protocol):
    id: str
    model: str
    def generate(self, messages, schema=None, max_tokens=None, temperature=0) -> LLMResult: ...
    def check(self) -> None: ...
    def unload(self) -> None: ...
    # LLMResult: text, input_tokens, output_tokens, latency_ms, finish_reason
```

- Stage 2 implements Ollama only. Stage 6 adds OpenAI, Gemini, and Anthropic, with model IDs checked against their docs at that point.
- Changing the LLM is a per-request config change. Embeddings are locked per knowledge base, and changing them triggers a re-index.
- Keys come from environment variables or a gitignored `.env`, are loaded as Pydantic `SecretStr`, and are never written to SQLite, logs, or traces.
- The API binds to `127.0.0.1`.
- Cloud providers require explicit opt-in per knowledge base, because document text leaves the machine.
- Document text goes inside delimited evidence blocks and is labelled as untrusted. The LLM has no tools. A prompt-injection test document stays in the test suite.

## 9. Evaluation plan

### Compared systems

| ID | System |
|---|---|
| A | Fixed 512/50 chunks, top-5 (baseline) |
| B | Single best global config, top-5 (control for chunking) |
| C | Per-document optimized chunks, top-5 |
| D | C + dynamic depth |
| E | D + neighbors and dedupe |
| F | E + evidence check |

### Measures

| Dimension | Measure | Method |
|---|---|---|
| Retrieval | Recall@budget, hit rate, recall@k, MRR | Evidence-span overlap |
| Faithfulness | Share of claims supported by evidence | `gemma4:e4b` judge; human spot-check, with agreement reported |
| Citations | Valid ID, correct document and locator, supports the claim | Code for the first two; judge and human for the last |
| Refusals | False-answer and false-refusal rates | Includes unanswerable questions |
| Latency | p50/p95 per step | Trace log |
| Tokens | Input and output | Provider counts |
| Cost of ingest | Optimization time, storage | Measured per document |

### Data separation

Separate by document, not just by question, so facts from test documents can't leak into tuning.

| Set | Source | Purpose |
|---|---|---|
| Optimizer questions | LLM | Picking configs at ingest; never final evidence |
| Dev set | LLM plus human review | Tuning thresholds |
| Held-out test set | Separate documents; human-written | Final report; run once per release |

### Human benchmark

- Start with about 30 human-written questions, including some unanswerable ones, and grow it later.
- Use public documents: SEC 10-K filings, CC-BY arXiv papers, and government reports. Record each source and licence, and commit a document only if its licence allows. Otherwise link to it.
- Write the questions in Stage 3, before the optimizer exists.
- With about 30 questions, confidence intervals will be wide. Small differences must be reported as inconclusive.

### Final report format

| System | Recall@budget (95% CI) | MRR | Faithfulness | Citation accuracy | False answers | p95 latency | Avg tokens |
|---|---|---|---|---|---|---|---|
| A–F | measured | measured | measured | measured | measured | measured | measured |

Also include the question count, paired differences against A and B, commit hash, models and digests, machine, known limitations, and a plain statement of what did not improve.

## 10. Project structure

```
adaptive-rag/
├── CLAUDE.md  README.md  pyproject.toml  .env.example  .gitignore
├── docs/          DESIGN.md  PROGRESS.md
├── src/adaptive_rag/
│   ├── api/       # FastAPI routes and schemas
│   ├── config.py  # settings
│   ├── db/        # SQLite connection, SQL migrations, queries
│   ├── loaders/   # base interface, pdf, docx, txt
│   ├── chunking/  # fixed, recursive, structure, semantic
│   ├── optimizer/ # profile, questions, scoring, selection, registry
│   ├── retrieval/ # baseline, query analysis, adaptive, neighbors, budget
│   ├── answering/ # prompts, generation, citations
│   ├── providers/ # base, ollama (others in Stage 6)
│   ├── vectorstore/ # thin Chroma wrapper
│   ├── ingest.py  # ingestion pipeline
│   └── evaluation/ # metrics, runner, report
├── benchmarks/    # public document sources, human benchmark, results
├── tests/         # unit, integration, fixtures (including messy PDFs)
└── data/          # gitignored: uploads, sqlite, chroma
```

## 11. MVP (Stage 2)

**Setup first:** run `git init` and create `.gitignore` before anything else, with `data/` and `.env` ignored. Create the conda env `adaptive-rag` on Python 3.11. Commit only when asked.

**Smoke test:** complete. Results are in `PROGRESS.md`.

**In scope:**

- Create and list knowledge bases.
- Upload PDF, DOCX, and TXT, with validation, duplicate detection, and clear extraction failures.
- Fixed 512/50 chunks with all required metadata.
- Ollama embeddings, stored in Chroma and SQLite.
- Fixed top-5 search within one knowledge base.
- Grounded answers with server-built citations and a basic "insufficient evidence" response.

**Endpoints:** `POST/GET /kbs`, `POST/GET /kbs/{id}/documents`, `DELETE /documents/{id}`, `GET /jobs/{id}`, `POST /kbs/{id}/query`, `GET /health`

**Out of scope:** optimizer, adaptive retrieval, other providers, frontend.

## 12. Roadmap

Each stage ends with user approval and updates to this file and `PROGRESS.md`.

### Stage 2: Baseline backend

- **Objective:** a working, tested baseline RAG.
- **Features:** everything in section 11.
- **Tasks:** environment setup, git, smoke test, schema, loaders, fixed chunker, providers, vector store, API.
- **Tests:** offset and page mapping, duplicates, bad files, knowledge base isolation, citation building, prompt injection, fake-provider unit tests, one real Ollama end-to-end test.
- **Acceptance:** upload → question → cited answer works for all three formats, tests and ruff pass, and memory and question-generation speed are measured.
- **Deliverable:** runnable API with baseline.

### Stage 3: Evaluation harness

- **Objective:** trustworthy measurement before any optimization.
- **Features:** metrics, question generator, runner, report, human benchmark.
- **Tasks:** fix PDF column misdetection on tables, span-overlap metrics, bias filters, bootstrap, baseline run, embedding model comparison, calibrate the score floor on dev data, measure wrong-focused `answered` responses.
- **Tests:** metrics checked against hand-calculated examples, span matching, leakage check between dev and test sets.
- **Acceptance:** reproducible baseline report, a reviewed benchmark, a score floor chosen from dev data only, and a reported wrong-focus rate.
- **Deliverable:** first real baseline numbers.

### Stage 4: Chunking optimization

- **Objective:** select configs by measurement and reuse them.
- **Features:** remaining candidates, profiler, selection rule, registry, re-test logic.
- **Tasks:** confirm the question count, build chunkers, enforce cost caps, wire into ingestion, measure regret.
- **Tests:** chunker offset checks, selection rule cases, cap enforcement, reuse and re-index triggers.
- **Acceptance:** B vs C reported honestly, cost per document measured, and caps never exceeded.
- **Deliverable:** optimizer plus results, even if C doesn't win.

### Stage 5: Adaptive retrieval

- **Objective:** replace fixed top-k with evidence-driven retrieval.
- **Features:** query analysis, dynamic depth, evidence check, neighbors, dedupe, diversity, budget.
- **Tasks:** tune on the dev set only, then run the feature-by-feature comparison.
- **Tests:** same-document expansion, no duplicates, budget never exceeded, direct/expansion marking, refusal behaviour.
- **Acceptance:** A–F held-out report complete, with any feature that doesn't help disabled by default.
- **Deliverable:** adaptive pipeline and report.

### Stage 6: BYOK

- **Objective:** optional cloud providers.
- **Features:** OpenAI, Gemini, and Anthropic adapters, per-knowledge-base embedding lock, cloud opt-in.
- **Tasks:** adapters, shared contract tests, re-index flow.
- **Tests:** mocked provider tests, secret-leak checks on logs and traces, re-index switchover; real API calls optional using the user's own keys.
- **Acceptance:** Ollama still works with no keys set, and no secrets appear anywhere.
- **Deliverable:** provider support and setup docs.

### Stage 7: Frontend

- **Objective:** a usable interface; framework decided at the start of this stage.
- **Features:** knowledge bases, upload progress, chat with citations, evidence view, evaluation results.
- **Tasks:** connect to the existing API with minimal backend changes.
- **Tests:** end-to-end flow and error states.
- **Acceptance:** a new user can complete the full flow.
- **Deliverable:** working UI.

### Stage 8: GitHub polish

- **Objective:** a portfolio-ready repo.
- **Features:** README, architecture diagram, CI (pytest and ruff with fake providers), results, demo.
- **Tasks:** clean-machine setup test, secret scan, MIT licence (final decision here).
- **Tests:** CI passing; setup steps followed from scratch.
- **Acceptance:** someone else can run it from the README, and every claim links to a real result.
- **Deliverable:** public release.

## 13. Top risks

| # | Risk | Reduction |
|---|---|---|
| 1 | Optimization doesn't beat a good fixed config | Control B and honest reporting |
| 2 | Noisy metrics from too few questions lead to false winners | Bootstrap intervals, tie goes to simplest, separate confirmation questions |
| 3 | Poor PDF extraction undermines everything downstream | Quality gate, messy PDF fixtures, loader interface, fallback to non-structure candidates |
| 4 | Local speed or memory limits make ingestion impractical | Stage 2 measurement, cost caps, lower question count if needed, resumable jobs, one model loaded at a time during ingestion, smaller fallback model |
| 5 | Weak insufficiency detection gives confident wrong answers | Three-layer check, unanswerable test questions, publishing the false-answer rate |

## 14. References

- Ollama: [EmbeddingGemma](https://ollama.com/library/embeddinggemma), [Gemma 4](https://ollama.com/library/gemma4), [Qwen 3.5](https://ollama.com/library/qwen3.5), [embeddings](https://docs.ollama.com/capabilities/embeddings), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [thinking](https://docs.ollama.com/capabilities/thinking), [FAQ](https://docs.ollama.com/faq)
- Models: [EmbeddingGemma model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card), [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4), [Qwen3.5-9B on Hugging Face](https://huggingface.co/Qwen/Qwen3.5-9B/tree/main)
- Chroma: [collection configuration](https://docs.trychroma.com/docs/collections/configure), [metadata filtering](https://docs.trychroma.com/docs/querying-collections/metadata-filtering)
- PDF: [PyMuPDF licence](https://pymupdf.readthedocs.io/en/latest/about.html)
- Research: [Is Semantic Chunking Worth the Computational Cost?](https://arxiv.org/html/2410.13070v1)
