import asyncio
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import pytest
from textual.widgets import Label, OptionList

from code_recall.app import CodeRecallApp, StartupScreen
from code_recall.config import Settings
from code_recall.domain import Provider, QuestionMode, QuestionSession
from code_recall.questions import QuestionService


class FakeQuestionService:
    async def prepare(self, provider: Provider, mode: QuestionMode) -> None:
        pass

    async def generate(self, provider: Provider, mode: QuestionMode) -> QuestionSession:
        return make_session(provider=provider, mode=mode)


class CancellableQuestionService(FakeQuestionService):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.first_cancelled = False
        self.calls = 0

    async def generate(self, provider: Provider, mode: QuestionMode) -> QuestionSession:
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.first_cancelled = True
                raise
        return make_session(provider=provider, mode=mode)


def make_session(
    provider: Provider = Provider.OLLAMA,
    mode: QuestionMode = QuestionMode.SYSTEM_DESIGN,
) -> QuestionSession:
    return QuestionSession(
        question="What status code means Not Found?",
        answers=("200", "404", "401", "500"),
        correct_index=1,
        explanation="HTTP 404 indicates that the requested resource was not found.",
        source_title="HTTP status codes",
        mode=mode,
        provider=provider,
    )


def make_app(settings: Settings) -> CodeRecallApp:
    return CodeRecallApp(settings, cast(QuestionService, FakeQuestionService()))


@pytest.mark.anyio
async def test_arrow_and_enter_submit_correct_answer(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 1
            app._show_question(1, make_session())
            await pilot.press("down", "enter")

            answer_options = app.query_one("#answer-options", OptionList)
            status = app.query_one("#feedback-status", Label)
            assert app.answer_submitted
            assert answer_options.disabled
            assert str(status.render()) == "Correct"
            assert "[CORRECT]" in str(answer_options.options[1].prompt)


@pytest.mark.anyio
async def test_stale_question_result_is_ignored(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 2

            app._show_question(1, make_session())

            assert app.active_session is None


@pytest.mark.anyio
async def test_enter_submits_incorrect_answer(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 1
            app._show_question(1, make_session())
            await pilot.press("enter")

            answer_options = app.query_one("#answer-options", OptionList)
            status = app.query_one("#feedback-status", Label)
            assert str(status.render()) == "Incorrect"
            assert "[YOUR CHOICE]" in str(answer_options.options[0].prompt)
            assert "[CORRECT]" in str(answer_options.options[1].prompt)


@pytest.mark.anyio
async def test_generation_error_exposes_retry(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 1

            app._show_generation_error(1, "Provider unavailable")

            assert not app.query_one("#btn-next").has_class("hidden")
            assert str(app.query_one("#source-label", Label).render()) == ""


@pytest.mark.anyio
async def test_new_generation_cancels_in_flight_request(make_settings: Callable[..., Settings]) -> None:
    service = CancellableQuestionService()
    with patch.object(StartupScreen, "run_startup_checks"):
        app = CodeRecallApp(make_settings(), cast(QuestionService, service))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 1
            app.generate_question(1, Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)
            await service.started.wait()

            app._generation_id = 2
            worker = app.generate_question(2, Provider.OLLAMA, QuestionMode.SYSTEM_DESIGN)
            await worker.wait()

            assert service.first_cancelled
            assert app.active_session == make_session()
