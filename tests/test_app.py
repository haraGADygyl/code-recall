import asyncio
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

import pytest
from textual.pilot import Pilot
from textual.widgets import Button, Label, OptionList

from code_recall.app import CodeRecallApp, ModePickerScreen, StartupScreen
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
            assert app.query_one("#btn-submit", Button).has_class("hidden")


@pytest.mark.anyio
async def test_submit_button_uses_highlighted_answer(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 1
            app._show_question(1, make_session())
            answer_options = app.query_one("#answer-options", OptionList)
            answer_options.highlighted = 1

            app.query_one("#btn-submit", Button).press()
            await pilot.pause()

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
            assert app.query_one("#btn-submit", Button).has_class("hidden")
            assert str(app.query_one("#source-label", Label).render()) == ""


@pytest.mark.anyio
async def test_new_session_restores_submit_button(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            app._generation_id = 1
            app._show_question(1, make_session())
            await pilot.press("enter")

            app.load_new_session()
            await pilot.pause()

            submit_button = app.query_one("#btn-submit", Button)
            assert not submit_button.has_class("hidden")
            assert not submit_button.disabled


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


async def open_picker(app: CodeRecallApp, pilot: Pilot[None]) -> ModePickerScreen:
    """Dismiss the startup screen and open the topic picker."""
    await pilot.pause()
    app.pop_screen()
    await pilot.pause()
    await pilot.press("ctrl+r")
    await pilot.pause()
    assert isinstance(app.screen, ModePickerScreen)
    return app.screen


@pytest.mark.anyio
async def test_picker_opens_on_the_current_topic(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings(DEFAULT_QUESTION_MODE="fastapi"))
        async with app.run_test() as pilot:
            picker = await open_picker(app, pilot)

            options = picker.query_one("#mode-options", OptionList)
            assert options.highlighted == list(QuestionMode).index(QuestionMode.FASTAPI)
            assert str(options.options[options.highlighted].prompt).startswith(">")


@pytest.mark.anyio
async def test_selecting_a_topic_generates_a_question_in_it(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            picker = await open_picker(app, pilot)

            options = picker.query_one("#mode-options", OptionList)
            options.highlighted = list(QuestionMode).index(QuestionMode.LANGCHAIN)
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.current_question_mode is QuestionMode.LANGCHAIN
            assert not isinstance(app.screen, ModePickerScreen)
            assert app.active_session is not None
            assert app.active_session.mode is QuestionMode.LANGCHAIN


@pytest.mark.anyio
async def test_clicking_a_topic_selects_it(make_settings: Callable[..., Settings]) -> None:
    """The picker is meant to be usable with the mouse, not only the keyboard."""
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await open_picker(app, pilot)
            target = list(QuestionMode).index(QuestionMode.REST_API)

            await pilot.click("#mode-options", offset=(4, 1 + target))
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.current_question_mode is QuestionMode.REST_API
            assert app.active_session is not None
            assert app.active_session.mode is QuestionMode.REST_API


@pytest.mark.anyio
async def test_escape_cancels_without_changing_topic(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await open_picker(app, pilot)

            await pilot.press("escape")
            await pilot.pause()

            assert not isinstance(app.screen, ModePickerScreen)
            assert app.current_question_mode is QuestionMode.SYSTEM_DESIGN
            assert app.active_session is None


@pytest.mark.anyio
async def test_reselecting_the_current_topic_does_not_regenerate(make_settings: Callable[..., Settings]) -> None:
    """Re-picking the active topic should not throw away the question already on screen."""
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await open_picker(app, pilot)

            await pilot.press("enter")
            await pilot.pause()

            assert app.current_question_mode is QuestionMode.SYSTEM_DESIGN
            assert app.active_session is None


@pytest.mark.anyio
async def test_picker_does_not_stack_on_itself(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            await open_picker(app, pilot)
            depth = len(app.screen_stack)

            await pilot.press("ctrl+r")
            await pilot.pause()

            assert len(app.screen_stack) == depth


@pytest.mark.anyio
async def test_topic_header_names_the_active_topic(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings(DEFAULT_QUESTION_MODE="fastapi"))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()

            app.load_new_session()
            await pilot.pause()

            assert str(app.query_one("#topic-label", Label).render()) == "Topic: FastAPI"


@pytest.mark.anyio
async def test_topic_header_follows_the_picker(make_settings: Callable[..., Settings]) -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = make_app(make_settings())
        async with app.run_test() as pilot:
            picker = await open_picker(app, pilot)

            options = picker.query_one("#mode-options", OptionList)
            options.highlighted = list(QuestionMode).index(QuestionMode.LANGCHAIN)
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert str(app.query_one("#topic-label", Label).render()) == "Topic: LangChain"
