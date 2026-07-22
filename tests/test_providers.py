from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from main import CodeRecallApp, MultipleChoiceQuestion


def make_question() -> MultipleChoiceQuestion:
    return MultipleChoiceQuestion(
        question="What does HTTP 404 mean?",
        correct_answer="The requested resource was not found.",
        distractors=[
            "The request was successful.",
            "Authentication is required.",
            "The server encountered an error.",
        ],
        explanation="A 404 response means the server could not find the requested resource.",
    )


def test_openai_chat_returns_parsed_model() -> None:
    question = make_question()
    message = SimpleNamespace(parsed=question, refusal=None)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    client = Mock()
    client.chat.completions.parse.return_value = response
    app = CodeRecallApp()
    app.current_provider = "ollama"

    with patch("main.OpenAI", return_value=client):
        result = app.llm_chat(
            [{"role": "user", "content": "Create a question"}],
            MultipleChoiceQuestion,
            provider="openai",
        )

    assert result is question
    assert client.chat.completions.parse.call_args.kwargs["response_format"] is MultipleChoiceQuestion


def test_openai_chat_reports_refusal() -> None:
    message = SimpleNamespace(parsed=None, refusal="Unable to comply")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    client = Mock()
    client.chat.completions.parse.return_value = response
    app = CodeRecallApp()
    app.current_provider = "openai"

    with (
        patch("main.OpenAI", return_value=client),
        pytest.raises(ValueError, match="Unable to comply"),
    ):
        app.llm_chat([{"role": "user", "content": "Create a question"}], MultipleChoiceQuestion)


def test_ollama_chat_validates_model_json() -> None:
    question = make_question()
    app = CodeRecallApp()
    app.current_provider = "ollama"

    with patch(
        "main.ollama.chat",
        return_value={"message": {"content": question.model_dump_json()}},
    ) as chat:
        result = app.llm_chat([{"role": "user", "content": "Create a question"}], MultipleChoiceQuestion)

    assert result == question
    assert chat.call_args.kwargs["format"] == MultipleChoiceQuestion.model_json_schema()
