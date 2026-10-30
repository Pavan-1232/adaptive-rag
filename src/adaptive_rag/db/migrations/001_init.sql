CREATE TABLE knowledge_bases (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    embedding_provider TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    embedding_version TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    embedding_prompt_version TEXT NOT NULL,
    collection_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE chunking_configs (
    id INTEGER PRIMARY KEY,
    strategy TEXT NOT NULL,
    size_tokens INTEGER NOT NULL,
    overlap_tokens INTEGER NOT NULL,
    chunker_version TEXT NOT NULL,
    UNIQUE (strategy, size_tokens, overlap_tokens, chunker_version)
);

-- status: pending -> indexing -> ready | failed. A replaced version becomes superseded,
-- then is deleted. Only ready documents are ever searched.
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    format TEXT NOT NULL CHECK (format IN ('pdf', 'docx', 'txt')),
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    replaces_document_id INTEGER,
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'indexing', 'ready', 'failed', 'superseded')),
    error TEXT,
    warnings TEXT NOT NULL DEFAULT '[]',
    locator_kind TEXT CHECK (locator_kind IN ('page', 'paragraph', 'line')),
    canonical_text TEXT,
    units TEXT,
    sections TEXT,
    extractor_version TEXT,
    chunking_config_id INTEGER REFERENCES chunking_configs (id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (kb_id, sha256),
    UNIQUE (kb_id, filename, version)
);
CREATE INDEX idx_documents_kb_status ON documents (kb_id, status);

-- start_char and end_char index documents.canonical_text. Locators are page, paragraph,
-- or line numbers, depending on documents.locator_kind.
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    locator_start INTEGER NOT NULL,
    locator_end INTEGER NOT NULL,
    section_heading TEXT,
    chunking_config_id INTEGER NOT NULL REFERENCES chunking_configs (id),
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES documents (id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE query_traces (
    id INTEGER PRIMARY KEY,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    retrieved TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    timings_ms TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
