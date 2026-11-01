"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration loaded from environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "CampusAssist AI"
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])

    # AI Provider configuration: 'gemini', 'ollama', or 'auto'
    ai_provider: str = Field(default="gemini")
    gemini_api_key: SecretStr | None = None
    llm_model: str = Field(default="gemini-3.5-flash")
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="minicpm-v4.6:1b")

    # Paths & Knowledge Base
    data_dir: str = "data"
    vector_store_dir: str = "data/vectorstore"
    chroma_collection: str = "campusassist_faq"

    # Embedding Model configuration
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_dir: str | None = None
    hf_hub_offline: bool | None = None

    # Chunking & Retrieval parameters
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    retrieval_top_k: int = Field(default=4, ge=1, le=10)
    retrieval_max_distance: float = Field(default=0.75, gt=0.0, le=2.0)
    max_document_bytes: int = Field(default=5_000_000, ge=1024, le=20_000_000)
    max_pdf_pages: int = Field(default=100, ge=1, le=500)


    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            val_str = value.strip()
            if val_str.startswith("[") and val_str.endswith("]"):
                import json
                try:
                    parsed = json.loads(val_str)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip().strip('"').strip("'") for origin in val_str.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level")
        return normalized

    @model_validator(mode="after")
    def validate_chunk_configuration(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached process settings."""
    return Settings()
