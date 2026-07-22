import logging
import os
from contextlib import suppress
from logging.handlers import RotatingFileHandler

from code_recall.app import CodeRecallApp
from code_recall.config import ENV_FILE, Settings, get_state_dir
from code_recall.content import ContentRepository
from code_recall.domain import Provider
from code_recall.providers import OllamaQuestionProvider, OpenAIQuestionProvider, QuestionProvider
from code_recall.questions import QuestionService


def configure_logging(settings: Settings) -> None:
    state_dir = get_state_dir()
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with suppress(OSError):
        state_dir.chmod(0o700)

    handler = RotatingFileHandler(
        state_dir / "code-recall.log",
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def warn_about_env_permissions() -> None:
    if not ENV_FILE.exists():
        return
    try:
        permissions = ENV_FILE.stat().st_mode & 0o777
    except OSError:
        return
    if permissions & 0o077:
        logging.getLogger(__name__).warning("%s contains secrets and should use permissions 0600", ENV_FILE)


def build_app(settings: Settings) -> CodeRecallApp:
    providers: dict[Provider, QuestionProvider] = {
        Provider.OPENAI: OpenAIQuestionProvider(settings),
        Provider.OLLAMA: OllamaQuestionProvider(settings),
    }
    question_service = QuestionService(ContentRepository(settings), providers)
    return CodeRecallApp(settings, question_service)


def main() -> None:
    os.umask(0o077)
    settings = Settings()
    configure_logging(settings)
    warn_about_env_permissions()
    build_app(settings).run()


if __name__ == "__main__":
    main()
