-- Follow-up questions (2026-11-09): what retrieval actually searched, the first question of
-- the chain, and the turn this one follows. NULL for traces written before this migration.
ALTER TABLE query_traces ADD COLUMN searched_question TEXT;
ALTER TABLE query_traces ADD COLUMN base_question TEXT;
ALTER TABLE query_traces ADD COLUMN follows_trace_id INTEGER;
