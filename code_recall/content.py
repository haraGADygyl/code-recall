import json
import os
import random
import stat
from pathlib import Path

from code_recall.config import Settings
from code_recall.domain import ContentError, Provider, QuestionMode, SourceMaterial


class ContentRepository:
    """Load and validate article or topic source material."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_mode(self, mode: QuestionMode, provider: Provider) -> None:
        if mode is QuestionMode.ARTICLES:
            self._validate_article_policy(provider)
            self._article_files()
            return
        self._topics(mode)

    def select(self, mode: QuestionMode, provider: Provider) -> SourceMaterial:
        if mode is QuestionMode.ARTICLES:
            self._validate_article_policy(provider)
            path = random.choice(self._article_files())
            return SourceMaterial(mode=mode, title=path.name, content=self._read_article(path))

        topic = random.choice(self._topics(mode))
        return SourceMaterial(mode=mode, title=topic, content=topic)

    def _validate_article_policy(self, provider: Provider) -> None:
        if provider is Provider.OPENAI and not self.settings.ALLOW_REMOTE_ARTICLES:
            raise ContentError(
                "Article mode with OpenAI is disabled. Set ALLOW_REMOTE_ARTICLES=true "
                "to permit sending article contents to OpenAI, or switch to Ollama."
            )

    def _article_files(self) -> list[Path]:
        root = self.settings.ARTICLES_DIR
        try:
            resolved_root = root.resolve(strict=True)
        except OSError as error:
            raise ContentError(f"Articles directory is unavailable: {root}") from error

        if not resolved_root.is_dir():
            raise ContentError(f"Articles path is not a directory: {root}")

        files: list[Path] = []
        try:
            candidates = list(resolved_root.glob("*.md"))
        except OSError as error:
            raise ContentError(f"Could not list articles in {root}") from error

        for candidate in candidates:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError):
                continue
            files.append(resolved)

        if not files:
            raise ContentError(f"No safe .md files found in {root}")
        return files

    def _read_article(self, path: Path) -> str:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as error:
            raise ContentError(f"Could not read article: {path.name}") from error

        try:
            with os.fdopen(descriptor, "rb") as article:
                file_stat = os.fstat(article.fileno())
                if not stat.S_ISREG(file_stat.st_mode):
                    raise ContentError(f"Article is not a regular file: {path.name}")
                if file_stat.st_size > self.settings.MAX_ARTICLE_BYTES:
                    raise ContentError(
                        f"Article {path.name} is too large ({file_stat.st_size} bytes); "
                        f"limit is {self.settings.MAX_ARTICLE_BYTES} bytes"
                    )
                data = article.read(self.settings.MAX_ARTICLE_BYTES + 1)
        except OSError as error:
            raise ContentError(f"Could not read article: {path.name}") from error

        if len(data) > self.settings.MAX_ARTICLE_BYTES:
            raise ContentError(f"Article {path.name} grew beyond the configured size limit while reading")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContentError(f"Article is not valid UTF-8: {path.name}") from error

    def _topics(self, mode: QuestionMode) -> list[str]:
        path = self._topic_path(mode)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ContentError(f"Topic file does not exist: {path}") from error
        except (OSError, UnicodeDecodeError) as error:
            raise ContentError(f"Could not read topic file: {path}") from error
        except json.JSONDecodeError as error:
            raise ContentError(f"Topic file contains invalid JSON: {path}") from error

        if not isinstance(raw, list) or not raw:
            raise ContentError(f"Topic file must contain a non-empty JSON list: {path}")
        if any(not isinstance(topic, str) or not topic.strip() for topic in raw):
            raise ContentError(f"Every topic must be a non-empty string: {path}")
        return [topic.strip() for topic in raw]

    def _topic_path(self, mode: QuestionMode) -> Path:
        paths = {
            QuestionMode.REST_API: self.settings.REST_API_TOPICS_FILE,
            QuestionMode.FASTAPI: self.settings.FASTAPI_TOPICS_FILE,
            QuestionMode.SYSTEM_DESIGN: self.settings.SYSTEM_DESIGN_TOPICS_FILE,
        }
        try:
            return paths[mode]
        except KeyError as error:
            raise ContentError(f"No topic file is configured for mode: {mode.value}") from error
