-- Stage 5: keyword index over chunk text for hybrid search (SQLite FTS5, BM25).
-- Stores its own copy of the text keyed by chunk id, so it never depends on rowids.
CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, text);
CREATE TRIGGER chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (chunk_id, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER chunks_fts_delete AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = old.id;
END;
CREATE TRIGGER chunks_fts_update AFTER UPDATE OF text ON chunks BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = old.id;
    INSERT INTO chunks_fts (chunk_id, text) VALUES (new.id, new.text);
END;
INSERT INTO chunks_fts (chunk_id, text) SELECT id, text FROM chunks;
