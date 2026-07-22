from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from code_recall.config import Settings
from code_recall.content import ContentRepository
from code_recall.domain import ContentError, Provider, QuestionMode


def test_openai_articles_require_explicit_opt_in(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    articles = tmp_path / "articles"
    articles.mkdir()
    (articles / "safe.md").write_text("Safe article", encoding="utf-8")
    repository = ContentRepository(make_settings(ARTICLES_DIR=articles))

    with pytest.raises(ContentError, match="ALLOW_REMOTE_ARTICLES"):
        repository.select(QuestionMode.ARTICLES, Provider.OPENAI)


def test_reads_safe_article_when_remote_upload_is_enabled(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    articles = tmp_path / "articles"
    articles.mkdir()
    (articles / "safe.md").write_text("Safe article", encoding="utf-8")
    repository = ContentRepository(make_settings(ARTICLES_DIR=articles, ALLOW_REMOTE_ARTICLES=True))

    source = repository.select(QuestionMode.ARTICLES, Provider.OPENAI)

    assert source.title == "safe.md"
    assert source.content == "Safe article"


def test_rejects_article_symlinks(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    articles = tmp_path / "articles"
    articles.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")
    (articles / "linked.md").symlink_to(outside)
    repository = ContentRepository(make_settings(ARTICLES_DIR=articles))

    with pytest.raises(ContentError, match="No safe"):
        repository.select(QuestionMode.ARTICLES, Provider.OLLAMA)


def test_rejects_file_replaced_by_symlink_before_open(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    articles = tmp_path / "articles"
    articles.mkdir()
    article = articles / "article.md"
    article.write_text("safe", encoding="utf-8")
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")
    repository = ContentRepository(make_settings(ARTICLES_DIR=articles))

    def replace_before_read() -> list[Path]:
        article.unlink()
        article.symlink_to(outside)
        return [article]

    with (
        patch.object(repository, "_article_files", side_effect=replace_before_read),
        pytest.raises(ContentError, match="Could not read"),
    ):
        repository.select(QuestionMode.ARTICLES, Provider.OLLAMA)


def test_rejects_oversized_articles(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    articles = tmp_path / "articles"
    articles.mkdir()
    (articles / "large.md").write_text("12345", encoding="utf-8")
    repository = ContentRepository(make_settings(ARTICLES_DIR=articles, MAX_ARTICLE_BYTES=4))

    with pytest.raises(ContentError, match="too large"):
        repository.select(QuestionMode.ARTICLES, Provider.OLLAMA)


@pytest.mark.parametrize("content", ["{}", "[]", '["valid", ""]', "not-json"])
def test_rejects_invalid_topic_files(make_settings: Callable[..., Settings], tmp_path: Path, content: str) -> None:
    topic_file = tmp_path / "topics.json"
    topic_file.write_text(content, encoding="utf-8")
    repository = ContentRepository(make_settings(SYSTEM_DESIGN_TOPICS_FILE=topic_file))

    with pytest.raises(ContentError):
        repository.select(QuestionMode.SYSTEM_DESIGN, Provider.OLLAMA)


def test_selects_valid_topic(make_settings: Callable[..., Settings], tmp_path: Path) -> None:
    topic_file = tmp_path / "topics.json"
    topic_file.write_text('["Load balancing"]', encoding="utf-8")
    repository = ContentRepository(make_settings(SYSTEM_DESIGN_TOPICS_FILE=topic_file))

    source = repository.select(QuestionMode.SYSTEM_DESIGN, Provider.OPENAI)

    assert source.title == "Load balancing"
    assert source.content == "Load balancing"
