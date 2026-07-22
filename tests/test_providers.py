from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from ollama import ResponseError as OllamaResponseError

from code_recall.config import Settings
from code_recall.domain import ConfigurationError, MultipleChoiceQuestion, ProviderError
from code_recall.providers import OllamaQuestionProvider, OpenAIQuestionProvider


def make_question() -> MultipleChoiceQuestion:
    return MultipleChoiceQuestion(
        question="What does HTTP 404 mean?",
        correct_answer="The requested resource was not found.",
        distractors=["Success.", "Authentication required.", "Server error."],
        explanation="A 404 means that the requested resource could not be found.",
    )


@pytest.mark.anyio
async def test_openai_requires_api_key(make_settings: Callable[..., Settings]) -> None:
    provider = OpenAIQuestionProvider(make_settings(OPENAI_API_KEY=""))

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        await provider.prepare()


@pytest.mark.anyio
async def test_openai_returns_parsed_question(make_settings: Callable[..., Settings]) -> None:
    question = make_question()
    message = SimpleNamespace(parsed=question, refusal=None)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    client = Mock()
    client.chat.completions.parse = AsyncMock(return_value=response)
    provider = OpenAIQuestionProvider(make_settings(OPENAI_API_KEY="test-key"))

    with patch.object(provider, "_get_client", return_value=client):
        result = await provider.generate([{"role": "user", "content": "Create a question"}])

    assert result is question
    assert client.chat.completions.parse.call_args.kwargs["response_format"] is MultipleChoiceQuestion


@pytest.mark.anyio
async def test_openai_reports_refusal(make_settings: Callable[..., Settings]) -> None:
    message = SimpleNamespace(parsed=None, refusal="No")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    client = Mock()
    client.chat.completions.parse = AsyncMock(return_value=response)
    provider = OpenAIQuestionProvider(make_settings(OPENAI_API_KEY="test-key"))

    with (
        patch.object(provider, "_get_client", return_value=client),
        pytest.raises(ProviderError, match="refused"),
    ):
        await provider.generate([{"role": "user", "content": "Create a question"}])


@pytest.mark.anyio
async def test_openai_rejects_empty_choices(make_settings: Callable[..., Settings]) -> None:
    client = Mock()
    client.chat.completions.parse = AsyncMock(return_value=SimpleNamespace(choices=[]))
    provider = OpenAIQuestionProvider(make_settings(OPENAI_API_KEY="test-key"))

    with (
        patch.object(provider, "_get_client", return_value=client),
        pytest.raises(ProviderError, match="no completion choices"),
    ):
        await provider.generate([{"role": "user", "content": "Create a question"}])


@pytest.mark.anyio
async def test_ollama_uses_schema_and_unloads_model(make_settings: Callable[..., Settings]) -> None:
    question = make_question()
    client = Mock()
    client.chat = AsyncMock(return_value=SimpleNamespace(message=SimpleNamespace(content=question.model_dump_json())))
    provider = OllamaQuestionProvider(make_settings(OLLAMA_KEEP_ALIVE="0"))
    provider._client = client

    result = await provider.generate([{"role": "user", "content": "Create a question"}])

    assert result == question
    assert client.chat.call_args.kwargs["format"] == MultipleChoiceQuestion.model_json_schema()
    assert client.chat.call_args.kwargs["keep_alive"] == "0"


@pytest.mark.anyio
async def test_ollama_connection_failure_starts_local_server(make_settings: Callable[..., Settings]) -> None:
    response = SimpleNamespace(models=[SimpleNamespace(model="gemma2:2b")])
    client = Mock()
    client.list = AsyncMock(side_effect=ConnectionError("offline"))
    provider = OllamaQuestionProvider(make_settings())
    provider._probe_client = client

    with (
        patch.object(provider, "_start_server") as start_server,
        patch.object(provider, "_wait_for_server", new=AsyncMock(return_value=response)),
    ):
        await provider.prepare()

    start_server.assert_called_once_with()


@pytest.mark.anyio
async def test_ollama_response_error_does_not_start_server(make_settings: Callable[..., Settings]) -> None:
    client = Mock()
    client.list = AsyncMock(side_effect=OllamaResponseError("denied", 401))
    provider = OllamaQuestionProvider(make_settings())
    provider._probe_client = client

    with (
        patch.object(provider, "_start_server") as start_server,
        pytest.raises(ProviderError, match="rejected"),
    ):
        await provider.prepare()

    start_server.assert_not_called()
