import os
from pathlib import Path
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from code_recall.domain import Provider, QuestionMode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded explicitly at the composition root."""

    MODEL_NAME: str = "gemma2:2b"
    OLLAMA_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)
    OLLAMA_PROBE_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)
    OLLAMA_KEEP_ALIVE: str = "0"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_NAME: str = "gpt-4.1-mini"
    OPENAI_TIMEOUT_SECONDS: float = Field(default=45.0, gt=0)
    OPENAI_MAX_RETRIES: int = Field(default=1, ge=0, le=5)

    DEFAULT_PROVIDER: Provider = Provider.OPENAI
    DEFAULT_QUESTION_MODE: QuestionMode = QuestionMode.SYSTEM_DESIGN

    ARTICLES_DIR: Path = PROJECT_ROOT / "articles"
    REST_API_TOPICS_FILE: Path = PROJECT_ROOT / "data/rest_api_topics.json"
    FASTAPI_TOPICS_FILE: Path = PROJECT_ROOT / "data/fastapi_topics.json"
    SYSTEM_DESIGN_TOPICS_FILE: Path = PROJECT_ROOT / "data/system_design_topics.json"

    ALLOW_REMOTE_ARTICLES: bool = False
    MAX_ARTICLE_BYTES: int = Field(default=262_144, gt=0)

    LOG_MAX_BYTES: int = Field(default=1_048_576, gt=0)
    LOG_BACKUP_COUNT: int = Field(default=3, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MODEL_NAME", "OPENAI_MODEL_NAME", "OLLAMA_KEEP_ALIVE")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        for field_name in (
            "ARTICLES_DIR",
            "REST_API_TOPICS_FILE",
            "FASTAPI_TOPICS_FILE",
            "SYSTEM_DESIGN_TOPICS_FILE",
        ):
            path = getattr(self, field_name).expanduser()
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            setattr(self, field_name, path.resolve(strict=False))
        self.OPENAI_API_KEY = self.OPENAI_API_KEY.strip()
        return self


def get_state_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local/state"
    return base / "code-recall"
