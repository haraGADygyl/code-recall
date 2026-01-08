from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings managed via environment variables and .env files.
    """

    # Model name for Ollama
    MODEL_NAME: str = "gemma2:2b"

    # Directory containing the markdown articles
    # Default is the local ./articles directory
    ARTICLES_DIR: Path = Path("./articles")

    # Pydantic Settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # This allows extra env vars without erroring
        extra="ignore",
    )


# Global settings instance
settings = Settings()
