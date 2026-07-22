from unittest.mock import patch

import pytest
from textual.widgets import Label, OptionList

from main import CodeRecallApp, StartupScreen


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def prepare_question(app: CodeRecallApp) -> None:
    app.current_question = "What status code means Not Found?"
    app.current_answers = ["200", "404", "401", "500"]
    app.current_correct_index = 1
    app.current_explanation = "HTTP 404 indicates that the requested resource was not found."
    app.show_question()


@pytest.mark.anyio
async def test_arrow_and_enter_submit_correct_answer() -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = CodeRecallApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            await prepare_question(app)
            await pilot.press("down", "enter")

            answer_options = app.query_one("#answer-options", OptionList)
            status = app.query_one("#feedback-status", Label)
            assert app.answer_submitted
            assert answer_options.disabled
            assert str(status.render()) == "Correct"
            assert "[CORRECT]" in str(answer_options.options[1].prompt)
            assert not app.query_one("#feedback-container").has_class("hidden")
            assert not app.query_one("#btn-next").has_class("hidden")


@pytest.mark.anyio
async def test_enter_submits_incorrect_answer() -> None:
    with patch.object(StartupScreen, "run_startup_checks"):
        app = CodeRecallApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            await prepare_question(app)
            await pilot.press("enter")

            answer_options = app.query_one("#answer-options", OptionList)
            status = app.query_one("#feedback-status", Label)
            assert str(status.render()) == "Incorrect"
            assert "[YOUR CHOICE]" in str(answer_options.options[0].prompt)
            assert "[CORRECT]" in str(answer_options.options[1].prompt)
