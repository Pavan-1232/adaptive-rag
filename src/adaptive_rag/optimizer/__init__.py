"""Evaluation-driven chunking: profile a document, test candidates on generated questions, pick
one by measured Recall@budget. Reuse of winning configs (the registry) is configuration caching
with rule-based profile matching. It is not machine learning."""
