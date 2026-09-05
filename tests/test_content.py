import os
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from code_recall.config import Settings
from code_recall.content import ContentRepository
from code_recall.domain import ContentError, QuestionMode


@pytest.mark.parametrize(
    "content",
    [
        "{}",
        "[]",
        '["valid", ""]',
        '{"Empty": []}',
        '{"Broken": "not-a-list"}',
        '{"One": ["duplicate"], "Two": ["DUPLICATE"]}',
        '{"Storage": ["One"], "storage": ["Two"]}',
        '{"Storage": ["One"], "Storage": ["Two"]}',
        "not-json",
    ],
)
def test_rejects_invalid_topic_files(make_settings: Callable[..., Settings], tmp_path: Path, content: str) -> None:
    topic_file = tmp_path / "topics.json"
    topic_file.write_text(content, encoding="utf-8")
    repository = ContentRepository(make_settings(SYSTEM_DESIGN_TOPICS_FILE=topic_file))

    with pytest.raises(ContentError):
        repository.select(QuestionMode.SYSTEM_DESIGN)


def test_missing_topic_file_reports_the_path(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    repository = ContentRepository(make_settings(ADVANCED_PYTHON_TOPICS_FILE=tmp_path / "absent.json"))

    with pytest.raises(ContentError, match="does not exist"):
        repository.validate_mode(QuestionMode.ADVANCED_PYTHON)


def test_selects_valid_topic(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.json"
    topic_file.write_text('["Load balancing"]', encoding="utf-8")
    repository = ContentRepository(make_settings(SYSTEM_DESIGN_TOPICS_FILE=topic_file))

    source = repository.select(QuestionMode.SYSTEM_DESIGN)

    assert source.title == "Load balancing"
    assert source.content == "Load balancing"
    assert source.category is None


def test_selects_category_before_topic(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.json"
    topic_file.write_text(
        '{"Reliability": ["Circuit breakers"], "Storage": ["Sharding"]}',
        encoding="utf-8",
    )
    repository = ContentRepository(make_settings(SYSTEM_DESIGN_TOPICS_FILE=topic_file))

    with patch("code_recall.content.random.choice", side_effect=["Reliability", "Circuit breakers"]) as choice:
        source = repository.select(QuestionMode.SYSTEM_DESIGN)

    assert choice.call_count == 2
    assert source.category == "Reliability"
    assert source.title == "Reliability: Circuit breakers"
    assert source.content == "Circuit breakers"


def test_explicit_general_category_is_preserved(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.json"
    topic_file.write_text('{"General": ["Architecture basics"]}', encoding="utf-8")
    repository = ContentRepository(make_settings(SYSTEM_DESIGN_TOPICS_FILE=topic_file))

    source = repository.select(QuestionMode.SYSTEM_DESIGN)

    assert source.category == "General"
    assert source.title == "General: Architecture basics"


CATEGORIZED_MODES = [
    QuestionMode.ADVANCED_PYTHON,
    QuestionMode.LANGCHAIN,
    QuestionMode.SYSTEM_DESIGN,
]


@pytest.mark.parametrize("mode", CATEGORIZED_MODES)
def test_categorized_catalogs_are_balanced(mode: QuestionMode) -> None:
    """Equal-sized categories keep category-first selection evenly weighted across topics."""
    with patch.dict(os.environ, {}, clear=True):
        repository = ContentRepository(Settings(_env_file=None))  # type: ignore[call-arg]

    catalog = repository._topic_catalog(mode)

    assert len(catalog) == 11
    assert all(len(topics) == 8 for topics in catalog.values())
    assert sum(len(topics) for topics in catalog.values()) == 88


@pytest.mark.parametrize("mode", list(QuestionMode))
def test_every_mode_ships_a_valid_topic_catalog(mode: QuestionMode) -> None:
    """Every selectable mode must resolve to a shipped catalog, so Ctrl+R can never stall."""
    with patch.dict(os.environ, {}, clear=True):
        repository = ContentRepository(Settings(_env_file=None))  # type: ignore[call-arg]

    repository.validate_mode(mode)
