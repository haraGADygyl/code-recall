from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import pytest

from code_recall.config import Settings
from code_recall.content import ContentRepository
from code_recall.domain import CodeRecallError, MultipleChoiceQuestion, Provider, ProviderError, QuestionMode
from code_recall.providers import ChatMessage, QuestionProvider
from code_recall.questions import QuestionService


def make_question(correct: int, distractors: tuple[int, int, int], tag: str = "a") -> MultipleChoiceQuestion:
    """Build a valid question whose answers have exactly the requested lengths."""
    return MultipleChoiceQuestion(
        question="What does a load balancer do?",
        correct_answer=f"{tag}C" + "x" * (correct - 2),
        distractors=[f"{tag}{index}" + "y" * (length - 2) for index, length in enumerate(distractors)],
        explanation="It spreads requests across available backends.",
    )


BALANCED = make_question(60, (58, 55, 51), tag="b")
UNBALANCED = make_question(114, (71, 61, 57), tag="u")
LESS_UNBALANCED = make_question(90, (71, 61, 57), tag="l")


class ScriptedProvider:
    """Returns a scripted result per call and records the messages it received."""

    def __init__(self, *results: MultipleChoiceQuestion | CodeRecallError) -> None:
        self.results = list(results)
        self.calls: list[list[ChatMessage]] = []

    async def prepare(self) -> None:
        return None

    async def generate(self, messages: list[ChatMessage]) -> MultipleChoiceQuestion:
        self.calls.append(messages)
        result = self.results[len(self.calls) - 1]
        if isinstance(result, CodeRecallError):
            raise result
        return result


def build_service(
    settings: Settings,
    provider: ScriptedProvider,
) -> QuestionService:
    settings.SYSTEM_DESIGN_TOPICS_FILE.write_text('{"Reliability": ["Load balancing"]}', encoding="utf-8")
    return QuestionService(
        settings,
        ContentRepository(settings),
        {Provider.OLLAMA: cast(QuestionProvider, provider)},
    )


@pytest.mark.anyio
async def test_service_generates_immutable_session(make_settings: Callable[..., Settings]) -> None:
    provider = ScriptedProvider(BALANCED)
    service = build_service(make_settings(), provider)

    with patch("code_recall.questions.random.shuffle"):
        session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert session.answers[0] == BALANCED.correct_answer
    assert session.correct_index == 0
    assert session.source_title == "Reliability: Load balancing"
    assert "multiple-choice" in provider.calls[0][0]["content"]
    assert "Reliability category" in provider.calls[0][1]["content"]


@pytest.mark.anyio
async def test_system_prompt_demands_answer_length_parity(make_settings: Callable[..., Settings]) -> None:
    provider = ScriptedProvider(BALANCED)
    service = build_service(make_settings(), provider)

    await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    system_prompt = provider.calls[0][0]["content"]
    assert "length parity" in system_prompt
    assert "must not be the longest" in system_prompt


@pytest.mark.anyio
async def test_balanced_question_is_returned_without_regenerating(make_settings: Callable[..., Settings]) -> None:
    provider = ScriptedProvider(BALANCED)
    service = build_service(make_settings(), provider)

    session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert len(provider.calls) == 1
    assert BALANCED.correct_answer in session.answers


@pytest.mark.anyio
async def test_unbalanced_question_is_regenerated_with_corrective_feedback(
    make_settings: Callable[..., Settings],
) -> None:
    provider = ScriptedProvider(UNBALANCED, BALANCED)
    service = build_service(make_settings(), provider)

    session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert len(provider.calls) == 2
    assert BALANCED.correct_answer in session.answers
    assert UNBALANCED.correct_answer not in session.answers

    correction = provider.calls[1][-1]
    assert correction["role"] == "user"
    assert "gave the answer away by length" in correction["content"]
    assert "114 characters" in correction["content"]
    assert "only 71" in correction["content"]


@pytest.mark.anyio
async def test_retry_prompt_differs_so_deterministic_providers_resample(
    make_settings: Callable[..., Settings],
) -> None:
    """Ollama generates at temperature zero, so an identical retry would be pointless."""
    provider = ScriptedProvider(UNBALANCED, BALANCED)
    service = build_service(make_settings(), provider)

    await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert provider.calls[0] != provider.calls[1]
    assert len(provider.calls[1]) == len(provider.calls[0]) + 1


@pytest.mark.anyio
async def test_exhausted_attempts_return_the_most_balanced_candidate(
    make_settings: Callable[..., Settings],
) -> None:
    provider = ScriptedProvider(UNBALANCED, LESS_UNBALANCED)
    service = build_service(make_settings(), provider)

    session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert len(provider.calls) == 2
    assert LESS_UNBALANCED.correct_answer in session.answers


@pytest.mark.anyio
async def test_exhausted_attempts_keep_the_earlier_candidate_when_the_retry_is_worse(
    make_settings: Callable[..., Settings],
) -> None:
    provider = ScriptedProvider(LESS_UNBALANCED, UNBALANCED)
    service = build_service(make_settings(), provider)

    session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert LESS_UNBALANCED.correct_answer in session.answers


@pytest.mark.anyio
async def test_failed_regeneration_falls_back_instead_of_erroring(make_settings: Callable[..., Settings]) -> None:
    provider = ScriptedProvider(UNBALANCED, ProviderError("rate limited"))
    service = build_service(make_settings(), provider)

    session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert UNBALANCED.correct_answer in session.answers


@pytest.mark.anyio
async def test_first_attempt_failure_still_propagates(make_settings: Callable[..., Settings]) -> None:
    provider = ScriptedProvider(ProviderError("ollama is down"))
    service = build_service(make_settings(), provider)

    with pytest.raises(ProviderError, match="ollama is down"):
        await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)


@pytest.mark.anyio
async def test_single_attempt_setting_disables_regeneration(make_settings: Callable[..., Settings]) -> None:
    provider = ScriptedProvider(UNBALANCED)
    service = build_service(make_settings(ANSWER_BALANCE_ATTEMPTS=1), provider)

    session = await service.generate(Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)

    assert len(provider.calls) == 1
    assert UNBALANCED.correct_answer in session.answers
