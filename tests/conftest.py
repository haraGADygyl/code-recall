import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from code_recall.config import Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "DEFAULT_PROVIDER": "ollama",
            "DEFAULT_QUESTION_MODE": "system-design",
            "ARTICLES_DIR": tmp_path / "articles",
            "REST_API_TOPICS_FILE": tmp_path / "rest.json",
            "FASTAPI_TOPICS_FILE": tmp_path / "fastapi.json",
            "SYSTEM_DESIGN_TOPICS_FILE": tmp_path / "system-design.json",
        }
        values.update(overrides)
        with patch.dict(os.environ, {}, clear=True):
            return Settings(**cast(Any, {"_env_file": None, **values}))

    return factory
