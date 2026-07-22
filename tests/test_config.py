import os
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from code_recall.config import PROJECT_ROOT, Settings, get_state_dir
from code_recall.domain import Provider, QuestionMode


def test_settings_construct_without_openai_key() -> None:
    settings = Settings(_env_file=None, OPENAI_API_KEY="")  # type: ignore[call-arg]

    assert settings.DEFAULT_PROVIDER is Provider.OPENAI
    assert settings.OPENAI_API_KEY == ""


def test_relative_paths_are_anchored_to_project_root() -> None:
    settings = Settings(_env_file=None, ARTICLES_DIR=Path("custom-articles"))  # type: ignore[call-arg]

    assert settings.ARTICLES_DIR == PROJECT_ROOT / "custom-articles"


def test_settings_parse_enums(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings(DEFAULT_PROVIDER="openai", DEFAULT_QUESTION_MODE="fastapi")

    assert settings.DEFAULT_PROVIDER is Provider.OPENAI
    assert settings.DEFAULT_QUESTION_MODE is QuestionMode.FASTAPI


@pytest.mark.parametrize("field", ["MODEL_NAME", "OPENAI_MODEL_NAME", "OLLAMA_KEEP_ALIVE"])
def test_rejects_blank_runtime_values(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: "   "})


def test_state_dir_uses_xdg_location(tmp_path: Path) -> None:
    with patch.dict(os.environ, {"XDG_STATE_HOME": str(tmp_path)}):
        assert get_state_dir() == tmp_path / "code-recall"
