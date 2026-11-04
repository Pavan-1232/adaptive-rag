-- Stage 4: C7 continuation chunks carry a table's title and header as context. The context is
-- shown to the LLM and embedded with the chunk, and its tokens count toward every budget.
ALTER TABLE chunks ADD COLUMN context_start INTEGER;
ALTER TABLE chunks ADD COLUMN context_end INTEGER;
ALTER TABLE chunks ADD COLUMN context_text TEXT;
ALTER TABLE chunks ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chunks ADD COLUMN is_table INTEGER NOT NULL DEFAULT 0;
