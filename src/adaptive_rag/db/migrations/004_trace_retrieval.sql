-- Stage 5: how evidence was chosen (mode, query type, parts, uncovered parts, stop reason).
ALTER TABLE query_traces ADD COLUMN retrieval TEXT;
