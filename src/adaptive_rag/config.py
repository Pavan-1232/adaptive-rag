"""Application settings, read from environment variables or a gitignored .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADAPTIVE_RAG_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    max_upload_bytes: int = 50 * 1024 * 1024

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b"
    embedding_model: str = "embeddinggemma:300m"
    num_ctx: int = 8192
    max_answer_tokens: int = 1024

    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 50
    embedding_batch_size: int = 32

    top_k: int = 5
    # Hard maximum. The 2500 target is for adaptive retrieval (Stage 5); baseline top-5 uses this.
    evidence_max_tokens: int = 4000
    evidence_target_tokens: int = 2500
    # Starting value, not calibrated. Stage 5 tunes it on dev questions, per embedding model.
    score_floor: float = 0.2

    @property
    def db_path(self) -> Path:
        return self.data_dir / "adaptive_rag.sqlite"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"
