"""Chroma in its own process (security finding, PROGRESS.md decision 73).

Chroma's HNSW index files can be written from buffers that still hold old process memory. In the
API process that memory can contain an API key, which then lands in data/chroma/. The store
therefore runs in a separate, freshly spawned process that never holds a key:
- "spawn" starts a new interpreter, so none of the parent's memory is copied into it;
- environment variables holding API keys are removed while it starts, so it can't inherit them;
- only the Chroma path, chunk ids, vectors and metadata are ever sent to it.
It exits on shutdown(), at normal interpreter exit, or when its parent process dies.
"""

import multiprocessing
import os
import threading
import time
from contextlib import contextmanager
from multiprocessing.managers import BaseManager
from pathlib import Path

from . import VectorStore


class StoreProcess(BaseManager):
    pass


StoreProcess.register("VectorStore", VectorStore)


def _exit_with_parent(parent_pid: int) -> None:
    """Runs in the store process: stop if the API process is killed, so no orphan holds Chroma."""

    def watch() -> None:
        while os.getppid() == parent_pid:
            time.sleep(1)
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


@contextmanager
def _api_keys_removed_from_environ():
    saved = {name: os.environ.pop(name) for name in list(os.environ) if "API_KEY" in name.upper()}
    try:
        yield
    finally:
        os.environ.update(saved)


def start_store_process(path: Path) -> tuple[StoreProcess, VectorStore]:
    """Start the store process. Keep the first value alive and call its shutdown() when done."""
    process = StoreProcess(ctx=multiprocessing.get_context("spawn"))
    with _api_keys_removed_from_environ():
        process.start(initializer=_exit_with_parent, initargs=(os.getpid(),))
    return process, process.VectorStore(path)
