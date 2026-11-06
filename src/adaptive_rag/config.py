"""Application settings, read from environment variables or a gitignored .env file."""

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # "null" in the environment sets an optional switch (e.g. ADAPTIVE_RAG_ADAPTIVE_DELTA) to None.
    model_config = SettingsConfigDict(
        env_prefix="ADAPTIVE_RAG_",
        env_file=".env",
        extra="ignore",
        env_parse_none_str="null",
        populate_by_name=True,
    )

    data_dir: Path = Path("data")
    max_upload_bytes: int = 50 * 1024 * 1024

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b"
    # Stage 6 cloud answer models: cost-sensitive defaults checked against each provider's docs
    # on 2026-11-06. Used only with the user's own key and the knowledge base's cloud opt-in.
    openai_model: str = "gpt-6-luna"
    gemini_model: str = "gemini-3.5-flash-lite"
    anthropic_model: str = "claude-haiku-5-5"
    # The user's own keys (BYOK). SecretStr masks them in repr, str and JSON dumps. Read them only
    # through providers.keys.api_key, never directly, so Stage 7 can add the OS keychain there.
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ADAPTIVE_RAG_OPENAI_API_KEY", "OPENAI_API_KEY")
    )
    gemini_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ADAPTIVE_RAG_GEMINI_API_KEY", "GEMINI_API_KEY")
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ADAPTIVE_RAG_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    cloud_timeout_s: float = 60.0
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
    evidence_target_tokens: int = 2560  # S's budget, equal to A's top-5 (decision 50)
    # Used when a model has no entry in score_floors. Not calibrated.
    score_floor: float = 0.2
    # Calibrated on dev questions, per embedding model. Scores don't carry across models.
    # Set inside the gap between out-of-scope and terse answerable top scores (2026-11-02).
    score_floors: dict[str, float] = {"embeddinggemma:300m": 0.25, "bge-m3:latest": 0.47}

    # Stage 5. "baseline" is fixed top_k. "adaptive" is opt-in until the held-out run supports it.
    # The adaptive_* defaults below are finalist S, chosen on dev by decision 49's rule.
    retrieval: str = "baseline"
    adaptive_split_parts: bool = True
    adaptive_delta: float | None = None
    adaptive_min_chunks: int = 3
    adaptive_gap_cutoff: bool = True
    adaptive_max_chunks: dict[str, int] = {
        "factual": 5,
        "table": 5,
        "multi_part": 8,
        "comparative": 10,
        "broad": 10,
    }
    adaptive_dedupe: bool = False
    adaptive_dedupe_jaccard: float = 0.9
    adaptive_merge_spans: bool = False
    # Per-document cap for comparative and broad questions (soft). None turns it off.
    adaptive_doc_cap: int | None = None
    adaptive_neighbors: bool = True
    adaptive_expand_threshold: float = 0.5
    # Measured deviation from DESIGN.md's 30%: the reserve lowered dev recall at 2560 (decision 54).
    adaptive_neighbor_reserve: float = 0.0
    # Hybrid keyword (SQLite FTS5) + vector search. Opt-in switch; off for S (decision 53).
    adaptive_hybrid: bool = False
    adaptive_keyword_weight: float = 0.05
    adaptive_keyword_pool: int = 10
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
