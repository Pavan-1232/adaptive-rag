"""Checks that held-out test material stays out of dev and tuning."""

from pathlib import Path

from .benchmark import BENCHMARK_DIR, load_manifest


def shared_documents(root: Path = BENCHMARK_DIR) -> list[str]:
    """Names and hashes that appear in both the dev and test sets."""
    documents = load_manifest(root)
    dev = [item for item in documents if item.set == "dev"]
    test = [item for item in documents if item.set == "test"]
    shared = {item.name for item in dev} & {item.name for item in test}
    shared |= {item.sha256 for item in dev} & {item.sha256 for item in test}
    return sorted(shared)
