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

    # Default "C1" (fixed 512/50), chosen after Stage 4: the optimizer picked C1 for all 9
    # documents and C7 didn't beat C1 on held-out data. Opt-in: "adaptive" (registry reuse or
    # per-document optimization, about 10 min per new document) or "C2".."C7" to force one.
    # "fixed": the Stage 2 chunker with the sizes below, kept for reproducing earlier runs.
    chunking: str = "C1"
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 50
    embedding_batch_size: int = 32

    top_k: int = 5
    # Hard maximum. The 2500 target is for adaptive retrieval (Stage 5); baseline top-5 uses this.
    evidence_max_tokens: int = 4000
    evidence_target_tokens: int = 2500
    # Used when a model has no entry in score_floors. Not calibrated.
    score_floor: float = 0.2
    # Calibrated on dev questions, per embedding model. Scores don't carry across models.
    # Set inside the gap between out-of-scope and terse answerable top scores (2026-11-02).
    score_floors: dict[str, float] = {"embeddinggemma:300m": 0.25, "bge-m3:latest": 0.47}

    # Stage 5. "baseline" is fixed top_k. "adaptive" is opt-in until the held-out run supports it.
    retrieval: str = "baseline"
    adaptive_split_parts: bool = True
    adaptive_delta: float | None = 0.15
    adaptive_min_chunks: int = 3
    adaptive_max_chunks: dict[str, int] = {"factual": 5, "table": 5, "multi_part": 8, "broad": 10}
    adaptive_dedupe: bool = True
    adaptive_dedupe_jaccard: float = 0.9
    adaptive_neighbors: bool = False
    adaptive_expand_threshold: float = 0.5
    adaptive_neighbor_reserve: float = 0.0
    # Name parts with no evidence above the floor in the prompt, so the answer can be partial.
    adaptive_part_notice: bool = True
    # Ask the model to name the row label and column header for every number it reports.
    table_prompt: bool = False
    # Dynamic-depth floor, kept apart from the evidence gate so the gate can be turned off in
    # evaluation runs without changing what adaptive retrieval selects. Same starting values.
    depth_floors: dict[str, float] = {"embeddinggemma:300m": 0.25, "bge-m3:latest": 0.47}

    def floor_for(self, embedding_model: str) -> float:
        return self.score_floors.get(embedding_model, self.score_floor)

    def depth_floor_for(self, embedding_model: str) -> float:
        return self.depth_floors.get(embedding_model, 0.25)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "adaptive_rag.sqlite"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"
