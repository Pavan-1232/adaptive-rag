-- Stage 6: cloud answer models send document text off the machine, so each knowledge base
-- must opt in explicitly. Off by default.
ALTER TABLE knowledge_bases ADD COLUMN allow_cloud INTEGER NOT NULL DEFAULT 0;
