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
| Evaluation judge | `gemma4:e4b` with an audit prompt, a code check of its quotes and numbers, and a comparison against gold (decided 2026-11-02) | Different model from the answer LLM; caught most planted errors in Stage 3 probes | `deepseek-r1:8b` | About 4x slower on this Mac and its error-catching wasn't measured. At 9.6 GB, memory is the concern. Fallback: `qwen3.5:4b` or a smaller Gemma |
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

### Candidates (maximum 7)

| ID | Strategy | Size / overlap (tokens) | Condition |
|---|---|---|---|
| C1 | Fixed | 512 / 50 | Always; the control |
| C2 | Recursive | 256 / 25 | Always |
| C3 | Recursive | 512 / 50 | Always |
| C4 | Recursive | 1024 / 100 | Always |
| C5 | Structure-aware | Up to 512 | Only if reliable headings are found |
| C6 | Semantic (embedding breakpoints) | Up to 512 | Skipped when cost caps are reached |
| C7 | Table-aware recursive | Up to 512 | Only if tables are detected. Tables become their own chunks, split only between rows; continuation chunks carry a second character range for the table title and header (added 2026-11-04) |

Semantic chunking is tested, not assumed better. A Vectara study found its extra cost wasn't backed by consistent gains.

**Product default (decided 2026-11-04, after the Stage 4 held-out run):** C1 is the default chunking (`chunking = "C1"`). The optimizer (`chunking = "adaptive"`) and C7 (`chunking = "C7"`) are opt-in settings; their code and tests stay. Reasons: the optimizer chose C1 for all 9 dev and test documents at about 10 minutes each, and C7 vs C1 on held-out data was inconclusive (table and overall). See `PROGRESS.md`, decision 44.

**How the candidates work (implemented in Stage 4):**

- **Recursive (C2–C4):** split at paragraphs, then lines, sentences, words and tokens, then merge greedily up to the size. Overlap is at most N trailing tokens of the previous chunk, starting at a sentence boundary where possible and never mid-word.
- **Structure-aware (C5):** chunks never cross a heading. Sections under 50 tokens merge into the next one. It runs only when headings look reliable: at least 3 sections, at least 60% of the text under a heading, a median section of at least 80 tokens, and no heading over 15 words.
- **Semantic (C6):** each sentence is embedded with one neighbour on each side. Cuts go where the distance between consecutive windows is above the 95th percentile. Groups over 512 tokens are split recursively, and groups under 64 tokens join the next group. There is no overlap. In the optimizer it embeds only the sampled regions.
- **Table-aware (C7):**
  - **Detection, by line rules:** a row is a line ending in 2 or more figures. A table needs at least 3 rows with a text label, so chart axis ticks don't count. The title is up to 6 lines above, stopping at a blank line, a sentence end, or a "Table N" line. A caption directly below is included.
  - **Chunking:** a table that fits is one chunk. A larger table is split only at line ends. Continuation chunks carry the title and header (at most 150 tokens) as a second character range.
  - **Context:** that range is put in front of the chunk text, both for embedding and in the LLM evidence. Text-only tables aren't detected.
- **Context is never free:** each chunk has `evidence_tokens` = text tokens + context tokens. Recall@budget, the optimizer's scoring, and the LLM evidence budget all charge `evidence_tokens`. Gold evidence is matched against the chunk's own range only, so context adds cost but no coverage.

### Question generation

1. Sample sections from the canonical text, spread across the document, without using chunk boundaries.
2. The LLM returns a question and an exact supporting quote, using a Pydantic schema with Ollama structured output.
3. Code locates the quote and stores its character span. If it can't be found, the question is dropped. Each evidence item is one required fact. It can list `alternatives`, which are other places stating the same fact, and covering any one of them counts.
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
| Recall@budget: share of evidence covered within 2560 retrieved tokens, the size of five 512-token chunks. Raised from 2000 on 2026-11-02, which fit only three 512-token chunks or one 1024-token chunk; results from the two budgets are not comparable | Primary |
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

- At most 7 candidates and 40 questions per document (30 selection, 10 confirmation).
- The smoke test measured a median of 5.6 s per question with `think=False`, so the 40-question limit stays.
- Sample about 25% of tokens, capped at 30,000. Documents of 30,000 tokens or fewer are evaluated in full. Samples are evenly spaced windows of 1,500 tokens. They snap to a line boundary within 400 characters, otherwise to a word boundary, and they never cut a detected table.
- Every candidate is scored on the chunks that touch the sample. Questions come only from the sample. Table questions are planned in proportion to the sample's table share: at least 3 when tables exceed 5% of it, and at most 3 per table.
- At most 60 LLM calls per document (40 accepted questions; rejected ones are replaced). Generation stops at 70% of the time budget. The LLM is unloaded before any embedding.
- A time budget of 12 minutes per document (starting value). Semantic chunking runs last, so it is the first candidate dropped. With fewer than 10 selection questions, the control C1 is kept.
- Selection questions come first. Confirmation gets at most a quarter of the accepted questions (10 of 40), chosen evenly across the document.
- When the time budget runs out, stop and keep the best result so far.
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
| Baseline | Fixed top-5 by cosine similarity, plus answer-key linking (below) when on | Reference for everything else | v1 |
| Query type | Rules only: factual, table lookup, multi-part, comparative, broad | Accuracy on labelled dev questions | v1 |
| Per-part retrieval | Rule-based split of multi-part questions; each part embedded and searched separately; coverage-first selection (added 2026-11-04, decision 46) | Part coverage, Recall over sent evidence | v1 |
| Dynamic depth | Fetch 30, then apply the cutoff rules below | Recall@budget, tokens used | v1 |
| Evidence check | Score gate, LLM status, citation validation, MCQ option check (gate 4, 2026-11-09: an option pick without an answer key in the evidence is withheld, and so is a pick that differs from a linked key); parts with no candidate above the floor are named as uncovered | False-answer and false-refusal rates | v1 |
| Table-reading prompt | Switch: when evidence contains a table (line-rule detector, `find_tables`), state the row label and column header for every number reported (decision 47). Not added when no table is detected | Gold-comparison correctness on dev table questions | v1, off unless dev shows a gain |
| MCQ answer-key rule | System-prompt rule: a listed option is not a fact, however detailed its wording; pick one only if the evidence states it ("Ans.", solution, or a separate answer-key list for the same set of questions, cited with the question). When evidence has options (`has_options`: 3+ distinct (a)–(d) markers), the rule is repeated after the evidence (2026-11-09, from real use) | Real Gemini test with an options-only passage; not in the benchmark | v1, always on |
| Answer-key linking | When the sent evidence holds an MCQ, add the same document's answer-key section as an `answer_key` chunk (algorithm below). Both retrieval modes. Setting `answer_keys`, on by default; evaluation runs turn it off with `--no-answer-keys` | Real-use check on the user's CA index; synthetic tests | v1, on (approved change to baseline retrieval, user, 2026-11-09) |
| Neighbors | Algorithm below | Recall gain vs extra tokens | v1 |
| Dedupe | Merge overlapping or adjacent spans of one document into one block, so chunk overlap is sent and charged once (`merge_spans`); drop near-identical chunks (`dedupe`) | Duplicate tokens removed | v1 |
| Diversity | Per-document cap for comparative and broad questions only (`doc_cap`, default 3). Soft: chunks over the cap are used only if other documents run out of candidates, so a single-document answer isn't starved | Sources covered, recall | v1 |
| Token budget | Greedy fill with hard limits | Never exceeded (tested) | v1 |
| Keyword + vector search (SQLite FTS5) | Hybrid: FTS5 BM25 hits join each pool; rank by cosine + weight × BM25 strength; floors stay on cosine (`hybrid`) | Comparison against vector-only, on dev only | v1 switch (user, 2026-11-05). **Off for S** (user, 2026-11-05): on dev it changed 3 questions (+2, −1, including the loss of `tbl-fed-05`) for recall within 0.002. It stays an opt-in switch |
| Cross-encoder reranking | Heavy dependency on 16 GB | Compare later | Later |
| LLM query rewriting, multi-hop | Extra LLM calls and latency. Rule-based splitting is v1 (above) | Compare later | Later |
| Per-entity coverage check | Harder comparative logic | Compare later | Later |

### Answer-key linking (approved 2026-11-09)

**Approved change to baseline retrieval** (user, 2026-11-09). Baseline was "fixed top-5"; with this on, it's fixed top-5 plus answer-key chunks for any MCQ in the evidence. The Stage 3–5 results (dev and held-out) were measured **without** it and stay labelled that way; new evaluation runs record `answer_keys` in their metadata, and `--no-answer-keys` reproduces the old setup.

1. Trigger: the sent evidence contains a complete (a)–(d) option set (`adaptive_rag/mcq.py`), whatever the question's wording. At most 2 documents per question.
2. Target question: the number the user gives ("question 1", "Q.7"), or the only MCQ of that document in view (none cut off at a chunk edge). Otherwise there is no target: the key is still added and the model matches it, but gate 4 doesn't compare the answer with a keyed option. (Changed 2026-11-09 after real use: matching by shared words picked the wrong MCQ.) All MCQ chunks of a document in the evidence are considered, including questions whose options run past a chunk's end.
3. Key: in the same document, the first "ANSWERS/HINTS" or "Answers to the Multiple Choice Questions" heading after the question, unless a "TEST YOUR KNOWLEDGE" heading comes in between (that key belongs to a later set). Positions are document character offsets, so overlapping chunks don't confuse it. If a question number in view isn't in the heading's chunk, the list is followed into up to 2 more chunks. Key lists with or without dots ("1. (a)", "1 (b)") are parsed.
4. The key chunk is added after the other evidence as `source = "answer_key"`, cited with its own page and labelled in the UI. It must fit the hard maximum (`evidence_max_tokens`, both modes); if not, the lowest-scored chunk without an MCQ or key is dropped, and if that isn't enough the key is skipped. The trace records the question number, keyed letter, added and dropped chunks, or the reason nothing was added.
5. Gate 4 uses the keyed letter only when there is a target: an answer that picks options, none of them the keyed one, is withheld.
6. **Future work:** cross-document linking (a question bank's source label, such as "Source: Study Unit 4, Practice Q.7", to the study-material PDF in the same knowledge base).

### Follow-up questions (approved 2026-11-09)

A short follow-up in the same chat ("what is the answer", "explain it simply") is answered with the previous question. Decisions (user, 2026-11-09): link by trace id on the server, rule-based detection, previous answer not used.

1. The chat sends `previous_trace_id`: the last successful turn of this knowledge base's chat. Failed turns are skipped, so an error doesn't break the chain; a turn asked after **New topic** is a boundary that is never crossed (changed 2026-11-09 after real use). The server uses it only if that trace exists and belongs to the same knowledge base; otherwise the question is answered on its own, with a warning. A follow-up can't reach into another knowledge base.
2. Follow-up rule (`answering/followup.py`, no LLM call): no words beyond filler and reference words ("what is the answer", "why?"), or a leading continuation ("and question 2?", "what about part (b)?"). A question with its own subject stands alone.
3. Retrieval searches the chain's **base** question (its first question) plus the follow-up, joined by " — ", so chains don't pile up. Answer-key linking still sees the question number.
4. The prompt adds, written by code, "This is a follow-up. The user's earlier question in this chat was: …" before the follow-up, JSON-quoted like the question. It is the user's own text, never document text.
5. When an answer gives only the keyed letter of an MCQ whose question is certain ("1. (a)"), the code adds that option's text from the evidence ("1. (a) Nil"); the prompt also asks for letter and text. The response returns `searched_question`; the UI shows "Searched: …" when it differs from what was typed. Traces store `searched_question`, `base_question` and `follows_trace_id` (migration 007).
6. Not used: the previous answer (traces don't store answer text). Open option if "explain it simply" proves weak in real use.

### Tutor explanation (approved 2026-11-09)

Opt-in: a toggle "Add a general explanation (not from your documents)", saved per browser, off by default. When on, after the grounded answer is final (all gates applied), a **second, separate model call** (`answering/explain.py`) explains the topic from general knowledge:

1. Its prompt has no evidence passages, only: the user's message (and the earlier question for a follow-up); **the question being explained** (an MCQ's stem and options, from a passage the grounded answer cited: the linked question when it's certain, else the only cited MCQ, else the one that clearly best matches the search; none rather than a guess); and the final grounded answer, with citation markers removed. Both are fenced as untrusted context. The prompt asks for a CA tutor's explanation (the rule or standard, the working with numbers, why each option is right or wrong, one line to remember), tells it it has no documents and must not cite or say what documents say, and to say plainly if its knowledge points to another option than the grounded answer. (Revised 2026-11-09: the first version didn't send the question, so it explained the answer blind.)
2. Its text goes to its own response fields (`explanation`, `explanation_label`, `explanation_error`), is never parsed for citations (any `[E1]` markers are removed), and can't change the grounded status, answer, citations or warnings. If it fails, the grounded answer is returned unchanged and the error goes to `explanation_error`. If the grounded answer fails, no explanation call is made.
3. It runs for every grounded status, including partial and not-enough-evidence (user decision). Label: "Explanation (general knowledge, not from your documents)" when the grounded status is `answered`; otherwise "Explanation (general knowledge, not from your documents — may differ from ICAI's answer, verify before relying on it)". Gate 4 still withholds an option pick in the grounded part.
4. The UI shows it in a separate box below the cited answer, plain text, no citation chips. Same provider as the answer; cloud still needs the knowledge base's opt-in. Traces record that it was requested, tokens, time and success, never its text. Evaluation runs never request it.

### Per-part retrieval (added 2026-11-04)

1. Rules split a multi-part question into parts: at "and" between clauses, "while also", "both … and", a second question mark, or a list of items. No LLM call.
2. Each part is embedded and searched separately (about 50 ms per part). Candidates are pooled per document, keeping each chunk's best score and the parts it matched.
3. Coverage-first selection: the best chunk for each part goes in first, then the rest fill by score under the same depth rules and budget.
4. A part with no candidate above the floor is recorded as uncovered in the trace and named in the prompt, so the answer should be `partial`.
5. A single-part question behaves exactly as without this feature.

### Dynamic depth

| Type | Min–max chunks (starting values) |
|---|---|
| Factual | 3–5 |
| Comparative | 5–10 |
| Broad | 8–15 |

Keep chunks in score order and stop at the first of:

- The chunk's score falls below the floor.
- The score falls below `top_score − delta`.
- The largest score gap in the range is reached. The range is positions `min_chunks` to the type's maximum; the gap after the maximum also counts, so a list with no real drop isn't cut early (`gap_cutoff`).
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

Implementation notes (2026-11-05): the reserve is a setting (`neighbor_reserve`). direct hits are limited to 70% of the budget when neighbors are on; neighbors may use the reserve plus any room direct hits left.

**Measured deviation (user's decision, 2026-11-05):** finalist S uses a neighbor reserve of **0**, not 30%. In dev sweep 2, at 2,560 tokens, the 30% reserve lowered recall over sent evidence from 0.854 to 0.834, because it leaves room for only 3 direct chunks. The 30% reserve stays available as a setting. Merging is the `merge_spans` switch and also applies to direct hits that overlap each other. A gap between non-touching chunks is joined with a newline.

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
- Keys come from the OS keychain (Stage 7, via `keyring`), then environment variables or a gitignored `.env`. They are handled as Pydantic `SecretStr` and are never written to SQLite, logs, or traces. The API is write-only for keys: `GET /keys` returns only each key's source.
- **One key-loading seam (Stage 6, 2026-11-06):** a single function returns the key for a provider, and adapters receive the key through their constructor; they never read the environment themselves. Stage 6's only source is settings (environment or `.env`). Stage 7 adds an OS-keychain source inside that function, without changing the adapters.
- **Cloud answer models (Stage 6):** OpenAI, Gemini and Anthropic answer questions only. Embeddings, optimizer question generation and the evaluation judge stay local. Defaults are cost-sensitive and set in `config.py` (`openai_model`, `gemini_model`, `anthropic_model`), checked against each provider's docs on 2026-11-06.
- **Vector store in its own process (security fix, 2026-11-06):** Chroma runs in a separate spawned process that never holds an API key, because its index files can contain leftover process memory. The API starts and stops it.
- The API binds to `127.0.0.1`. It accepts only `Host` values of `127.0.0.1` or `localhost`, and refuses changing requests whose `Origin` or `Sec-Fetch-Site` shows another site (Stage 7). The UI is served from the same origin and calls `/api/...`; the prefix is stripped, so routes keep their paths.
- Cloud providers require explicit opt-in per knowledge base, because document text leaves the machine.
- **One retry for temporary cloud errors (2026-11-09):** a timeout or HTTP 429, 500, 502, 503 or 504 is retried once, after `Retry-After` (capped at 5 s) or 1 s. 400, 401, 403 and every other client error are never retried. The error rules above still hold (no key or provider text in messages); a final failure says it was retried.
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

**Stage 4 change (2026-11-04):** on dev, the optimizer chose C1 for every document and B was C1, so A, B and C were the same system. The Stage 4 held-out run therefore compares A (C1) with C7 table-aware as one fixed config, and with C (the optimizer). It is pre-registered in `PROGRESS.md`, decision 42. Later stages use whichever of these the held-out result supports as their chunking base. **Result:** C7 vs A inconclusive and C = A, so Stage 5 builds on A (C1).

### Measures

| Dimension | Measure | Method |
|---|---|---|
| Retrieval | Recall@budget, hit rate, recall@k, MRR | Evidence-span overlap |
| Faithfulness | Share of claims supported by evidence | `gemma4:e4b` judge, where a claim counts only if the judge supports it and its quote passes the code check; human spot-check, with agreement reported |
| Correctness | Agreement with the gold answer or quote | `gemma4:e4b` gold comparison. Catches wrong answers that are faithful to the wrong passage, which faithfulness can't see |
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
| Held-out test set | Separate documents. Stage 3 set: 30 questions written by Claude in a separate session, with 5 spot-checked by the user; a human-written subset is still the goal | Final report; run once per release |

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
- **Tasks:** confirm the question count, build chunkers, enforce cost caps, wire into ingestion, measure regret, and retest `bge-m3:latest` against `embeddinggemma:300m`, specifically on table questions.
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
- **Outcome (2026-11-05):** on held-out data, S vs A was inconclusive on recall over sent evidence (−0.019, CI −0.144 to +0.106), with 11% fewer tokens and all guardrails passed. `retrieval = "baseline"` stays the default; adaptive retrieval is opt-in with all its switches (`PROGRESS.md` decision 57).

### Stage 5b: Table extraction (added 2026-11-04, decision 47; deferred 2026-11-05 as the top future-work item, decision 58)

- **Objective:** fix table reading errors at the source by keeping table structure (row labels and column headers) in the extracted text.
- **Why separate:** it changes the loader and chunk text and needs a reindex, so it would confound the Stage 5 retrieval comparison.
- **Acceptance:** dev table correctness measured before and after; one held-out check; extractor version bumped so stale indexes are detected.

### Stage 6: BYOK

- **Objective:** optional cloud providers.
- **Features:** OpenAI, Gemini, and Anthropic adapters, per-knowledge-base embedding lock, cloud opt-in.
- **Tasks:** adapters, shared contract tests, re-index flow.
- **Tests:** mocked provider tests, secret-leak checks on logs and traces, re-index switchover; real API calls optional using the user's own keys.
- **Acceptance:** Ollama still works with no keys set, and no secrets appear anywhere.
- **Deliverable:** provider support and setup docs.
- **Outcome (2026-11-06):** OpenAI, Gemini and Anthropic answer adapters over `httpx`, a per-knowledge-base `allow_cloud` opt-in checked before any call, and keys from the environment through one key-loading function. Canary-key leak tests cover logs, traces, the database, files, errors and API responses. Real calls are off by default (`PROGRESS.md`, Stage 6 results).

### Stage 7: Frontend

- **Objective:** a usable interface; framework decided at the start of this stage.
- **Approach (approved 2026-11-06):** React, TypeScript, Vite and Tailwind, built directly. Served by FastAPI from the same origin, with no CORS and with `Host` and origin checks. Knowledge-base deletion with a confirm step. Keys stored in the OS keychain via `keyring`, checked before `.env`; the UI shows only each key's source. Evaluation verdicts in plain words. Details in `PROGRESS.md`, Stage 7 plan.
- **Features:** knowledge bases, upload progress, chat with citations, evidence view, evaluation results.
- **API keys in the UI (required, user's BYOK goal, 2026-11-06):** users enter their own OpenAI, Gemini and Anthropic keys in the UI. Keys are stored securely on the local machine, for example in the OS keychain. They are never stored as plain text in the database or written to logs. This plugs into Stage 6's key-loading seam.
- **Tasks:** connect to the existing API with minimal backend changes.
- **Tests:** end-to-end flow and error states.
- **Acceptance:** a new user can complete the full flow.
- **Outcome (2026-11-06):** built as planned in `frontend/`, served by FastAPI from `frontend/dist`. New endpoints: `DELETE /kbs/{id}`, `GET/PUT/DELETE /keys`, `GET /evaluation`. Citations carry the full passage. Details in `PROGRESS.md`, Stage 7 results.
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
