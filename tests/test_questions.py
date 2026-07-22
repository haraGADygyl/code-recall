from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import pytest

from code_recall.config import Settings
from code_recall.content import ContentRepository
from code_recall.domain import MultipleChoiceQuestion, Provider, QuestionMode
from code_recall.providers import ChatMessage, QuestionProvider
from code_recall.questions import QuestionService


class FakeProvider:
    def __init__(self) -> None:
        self.prepared = False
        self.messages: list[ChatMessage] = []

    async def prepare(self) -> None:
        self.prepared = True

    async def generate(self, messages: list[ChatMessage]) -> MultipleChoiceQuestion:
        self.messages = messages
        return MultipleChoiceQuestion(
            question="What does a load balancer do?",
            correct_answer="Distributes traffic across servers.",
            distractors=["Stores passwords.", "Compiles code.", "Creates database tables."],
            explanation="It spreads requests across available backends.",
        )


@pytest.mark.anyio
async def test_service_generates_immutable_session(make_settings: Callable[..., Settings]) -> None:
    settings = make_settings()
    settings.SYSTEM_DESIGN_TOPICS_FILE.write_text('["Load balancing"]', encoding="utf-8")
    provider = FakeProvider()
    service = QuestionService(
        ContentRepository(settings),
        {Provider.OLLAMA: cast(QuestionProvider, provider)},
    )

    with patch("code_recall.questions.random.shuffle"):
        session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert session.answers[0] == "Distributes traffic across servers."
    assert session.correct_index == 0
    assert session.source_title == "Load balancing"
    assert "multiple-choice" in provider.messages[0]["content"]
