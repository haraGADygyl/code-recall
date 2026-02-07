from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings managed via environment variables and .env files.
    """

    # Ollama configuration
    MODEL_NAME: str = "gemma2:2b"

    # OpenAI configuration
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_NAME: str = "gpt-4.1-mini"

    # Default LLM provider: "openai" or "ollama"
    DEFAULT_PROVIDER: Literal["openai", "ollama"] = "openai"

    # Default question mode: "articles" or "rest-api"
    DEFAULT_QUESTION_MODE: Literal["articles", "rest-api"] = "rest-api"

    # Directory containing the markdown articles
    # Default is the local ./articles directory
    ARTICLES_DIR: Path = Path("./articles")

    # REST API topics file for question generation
    REST_API_TOPICS_FILE: Path = Path("./data/rest_api_topics.json")

    # Pydantic Settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # This allows extra env vars without erroring
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_openai_api_key(self) -> Self:
        """Ensure OPENAI_API_KEY is set when DEFAULT_PROVIDER is 'openai'."""
        if self.DEFAULT_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY must be set when DEFAULT_PROVIDER is 'openai'. "
                "Set it in your .env file or switch to DEFAULT_PROVIDER='ollama'."
            )
        return self


# Global settings instance
settings = Settings()
