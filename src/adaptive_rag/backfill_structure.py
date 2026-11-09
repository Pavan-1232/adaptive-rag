"""Parse document structure for documents indexed before Stage 5b, from their stored text.

    python -m adaptive_rag.backfill_structure            # the app's data folder
    python -m adaptive_rag.backfill_structure DATA_DIR   # another data folder

No re-upload and no re-embedding: it reads the canonical text saved at upload.
"""

import sys
from pathlib import Path

from adaptive_rag.config import Settings
from adaptive_rag.db import connect, migrate
from adaptive_rag.structure import backfill


def main() -> int:
    settings = Settings() if len(sys.argv) < 2 else Settings(data_dir=Path(sys.argv[1]))
    conn = connect(settings.db_path)
    migrate(conn)
    with conn:
        done = backfill(conn)
    for filename, rows, refs in done:
        print(f"{filename}: {rows} contents rows, {refs} references")
    print(f"{len(done)} documents parsed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
