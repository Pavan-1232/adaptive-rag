-- Stage 5b (2026-11-09): document structure for exact lookups (adaptive_rag/structure.py).
-- Rows go with their document (ON DELETE CASCADE); character offsets point into canonical_text,
-- so a row maps to whichever chunk holds it under any chunking.
CREATE TABLE doc_contents (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    title TEXT NOT NULL,
    title_key TEXT NOT NULL,
    question_count INTEGER,
    page_start INTEGER NOT NULL,
    page_end INTEGER,
    header TEXT,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    locator INTEGER NOT NULL,
    page_offset INTEGER
);
CREATE INDEX doc_contents_document ON doc_contents (document_id);

CREATE TABLE doc_references (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    ref_key TEXT NOT NULL,
    short_key TEXT NOT NULL,
    entry INTEGER,
    is_header INTEGER NOT NULL,
    chapter TEXT,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    locator INTEGER NOT NULL
);
CREATE INDEX doc_references_short_key ON doc_references (short_key);
CREATE INDEX doc_references_document ON doc_references (document_id);

ALTER TABLE documents ADD COLUMN structure_version TEXT;
