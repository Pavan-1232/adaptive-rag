-- Stage 4: configuration registry. Winning chunking configs saved with the profile of the
-- document they won on, for reuse on similar documents. Configuration caching, not ML.
CREATE TABLE chunking_registry (
    id INTEGER PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    strategy TEXT NOT NULL,
    size_tokens INTEGER NOT NULL,
    overlap_tokens INTEGER NOT NULL,
    chunker_version TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_digest TEXT NOT NULL,
    embedding_prompt_version TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    profile_version TEXT NOT NULL,
    profile TEXT NOT NULL,
    selection_recall REAL,
    confirmation_recall REAL,
    question_count INTEGER NOT NULL,
    runtime_s REAL NOT NULL,
    source_document TEXT NOT NULL,
    times_reused INTEGER NOT NULL DEFAULT 0,
    last_retest TEXT,
    stale INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per chunking decision at ingest: what was done and why, with the full result.
CREATE TABLE optimization_runs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES documents (id) ON DELETE SET NULL,
    registry_id INTEGER REFERENCES chunking_registry (id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    detail TEXT NOT NULL,
    seconds REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
