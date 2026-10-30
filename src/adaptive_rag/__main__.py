"""Run the API locally: python -m adaptive_rag"""

import uvicorn


def main() -> None:
    # One worker only: Chroma's PersistentClient and the ingest lock assume a single process.
    uvicorn.run("adaptive_rag.api:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
