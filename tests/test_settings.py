import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from settings import Settings


def _make_settings(**overrides: str) -> Settings:
    """Create Settings with a clean environment, applying only the given overrides."""
    env = {
        "DEFAULT_PROVIDER": "ollama",
        "OPENAI_API_KEY": "",
        "MODEL_NAME": "gemma2:2b",
        "OPENAI_MODEL_NAME": "gpt-4.1-mini",
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)  # type: ignore[call-arg]


class TestSettingsDefaults:
    def test_default_model_name(self) -> None:
        s = _make_settings()
        assert s.MODEL_NAME == "gemma2:2b"

    def test_default_openai_model_name(self) -> None:
        s = _make_settings()
        assert s.OPENAI_MODEL_NAME == "gpt-4.1-mini"

    def test_default_articles_dir(self) -> None:
        s = _make_settings()
        assert Path("./articles") == s.ARTICLES_DIR

    def test_default_provider_is_openai(self) -> None:
        s = _make_settings(DEFAULT_PROVIDER="openai", OPENAI_API_KEY="test-key")
        assert s.DEFAULT_PROVIDER == "openai"


class TestSettingsValidation:
    def test_openai_provider_requires_api_key(self) -> None:
        with pytest.raises(ValidationError, match="OPENAI_API_KEY must be set"):
            _make_settings(DEFAULT_PROVIDER="openai", OPENAI_API_KEY="")

    def test_openai_provider_accepts_valid_key(self) -> None:
        s = _make_settings(DEFAULT_PROVIDER="openai", OPENAI_API_KEY="sk-test123")
        assert s.OPENAI_API_KEY == "sk-test123"

    def test_ollama_provider_does_not_require_api_key(self) -> None:
        s = _make_settings(DEFAULT_PROVIDER="ollama", OPENAI_API_KEY="")
        assert s.DEFAULT_PROVIDER == "ollama"

    def test_invalid_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DEFAULT_PROVIDER="invalid")


class TestSettingsOverrides:
    def test_custom_model_name(self) -> None:
        s = _make_settings(MODEL_NAME="llama3:8b")
        assert s.MODEL_NAME == "llama3:8b"

    def test_custom_articles_dir(self) -> None:
        s = _make_settings(ARTICLES_DIR="/tmp/articles")
        assert Path("/tmp/articles") == s.ARTICLES_DIR
