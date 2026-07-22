import logging
from typing import cast

from rich.markdown import Markdown
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, LoadingIndicator, OptionList, Static

from code_recall.config import Settings
from code_recall.domain import (
    MODE_LABELS,
    CodeRecallError,
    Provider,
    QuestionMode,
    QuestionSession,
)
from code_recall.questions import QuestionService

logger = logging.getLogger(__name__)


class StartupScreen(Screen[None]):
    """Prepare the selected provider and validate the initial question source."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("CodeRecall Setup", id="startup-title"),
            LoadingIndicator(id="startup-loader"),
            Label("Initializing...", id="status-label"),
            Horizontal(
                Button("Retry", id="startup-retry", classes="hidden", variant="primary"),
                Button("Quit", id="startup-quit", classes="hidden", variant="error"),
                id="startup-actions",
            ),
            id="startup-container",
        )

    def on_mount(self) -> None:
        self.run_startup_checks()

    @work(exclusive=True, group="startup", exit_on_error=False)
    async def run_startup_checks(self) -> None:
        app = cast("CodeRecallApp", self.app)
        self._show_checking()
        try:
            await app.question_service.prepare(app.current_provider, app.current_question_mode)
        except CodeRecallError as error:
            self._show_failure(str(error))
            return
        except Exception:
            logger.exception("Unexpected startup failure")
            self._show_failure("Unexpected startup failure. Check the application log.")
            return

        self._finish_startup()

    def _show_checking(self) -> None:
        app = cast("CodeRecallApp", self.app)
        provider = "OpenAI" if app.current_provider is Provider.OPENAI else "Ollama"
        self.query_one("#status-label", Label).update(f"Checking {provider} and question sources...")
        self.query_one("#startup-loader").remove_class("hidden")
        self.query_one("#startup-retry").add_class("hidden")
        self.query_one("#startup-quit").add_class("hidden")

    def _show_failure(self, message: str) -> None:
        self.query_one("#status-label", Label).update(f"ERROR: {message}")
        self.query_one("#startup-loader").add_class("hidden")
        self.query_one("#startup-retry").remove_class("hidden")
        self.query_one("#startup-quit").remove_class("hidden")
        self.query_one("#startup-retry", Button).focus()

    def _finish_startup(self) -> None:
        app = cast("CodeRecallApp", self.app)
        app.pop_screen()
        app.load_new_session()

    @on(Button.Pressed, "#startup-retry")
    def retry_startup(self) -> None:
        self.run_startup_checks()

    @on(Button.Pressed, "#startup-quit")
    def quit_startup(self) -> None:
        self.app.exit()


class CodeRecallApp(App[None]):
    CSS = """
    Screen {
        align: center middle;
        background: #1e1e1e;
        overflow-y: scroll;
    }

    #startup-container {
        width: 60%;
        height: auto;
        border: solid green;
        padding: 2;
        align: center middle;
    }

    #startup-title {
        text-align: center;
        text-style: bold;
        color: #00ff00;
        margin-bottom: 2;
    }

    #startup-actions {
        align: center middle;
        height: auto;
        margin-top: 1;
    }

    #main-container {
        width: 90%;
        height: 90%;
        border: solid #00ff00;
        padding: 1 2;
        layout: vertical;
    }

    #interaction-area {
        height: auto;
    }

    .hidden {
        display: none;
    }

    #question-box {
        height: auto;
        border-bottom: solid #444;
        margin-bottom: 1;
        padding: 1;
        background: #252525;
        overflow-y: auto;
    }

    #source-label {
        width: 100%;
        color: #888;
        margin-bottom: 1;
    }

    .correct {
        color: #00ff00;
        text-style: bold;
    }

    .incorrect {
        color: #ff0000;
        text-style: bold;
    }

    #answer-options {
        height: auto;
        max-height: 12;
        border: solid #555;
    }

    .feedback-box {
        height: 1fr;
        border-top: solid #444;
        padding: 1;
        background: #222;
        overflow-y: scroll;
        margin-top: 1;
    }

    #model-answer-label {
        color: #aaa;
        text-style: bold;
        margin-top: 1;
    }

    Button {
        margin: 0 2;
        width: 20;
    }

    #button-bar {
        align: center middle;
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+n", "next_question", "Next"),
        ("ctrl+t", "toggle_provider", "Toggle Provider"),
        ("ctrl+r", "toggle_question_mode", "Toggle Mode"),
    ]

    def __init__(self, settings: Settings, question_service: QuestionService) -> None:
        super().__init__()
        self.settings = settings
        self.question_service = question_service
        self.current_provider = settings.DEFAULT_PROVIDER
        self.current_question_mode = settings.DEFAULT_QUESTION_MODE
        self.active_session: QuestionSession | None = None
        self.answer_submitted = False
        self._generation_id = 0
        self._provider_check_pending = False

    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            yield Label("Loading Question...", id="main-status")

            with Vertical(id="interaction-area", classes="hidden"):
                yield Static("", id="question-box")
                yield Label("", id="source-label")
                yield OptionList(id="answer-options", markup=False)
                with Horizontal(id="button-bar"):
                    yield Button("Next Question", id="btn-next", classes="hidden", variant="success")
                    yield Button("Quit", id="btn-quit", variant="error")

            with Vertical(id="feedback-container", classes="hidden feedback-box"):
                yield Label("", id="feedback-status")
                yield Static("", id="feedback-content")
                yield Label("Correct Answer:", id="model-answer-label", classes="hidden")
                yield Static("", id="model-answer-content", classes="hidden")

        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(StartupScreen())

    def action_toggle_provider(self) -> None:
        if self._provider_check_pending:
            self.notify("A provider check is already running.", severity="warning")
            return
        target = Provider.OLLAMA if self.current_provider is Provider.OPENAI else Provider.OPENAI
        self._provider_check_pending = True
        self.notify(f"Checking {target.value}...", severity="information")
        self.verify_and_switch_provider(target, self.current_question_mode)

    @work(exclusive=True, group="provider", exit_on_error=False)
    async def verify_and_switch_provider(self, provider: Provider, mode: QuestionMode) -> None:
        try:
            await self.question_service.prepare(provider, mode)
        except CodeRecallError as error:
            self._provider_switch_failed(str(error))
            return
        except Exception:
            logger.exception("Unexpected provider preparation failure")
            self._provider_switch_failed("Could not switch providers. Check the application log.")
            return

        self._complete_provider_switch(provider)

    def _complete_provider_switch(self, provider: Provider) -> None:
        self._provider_check_pending = False
        self.current_provider = provider
        self.notify(f"Switched to {provider.value}", severity="information")

    def _provider_switch_failed(self, message: str) -> None:
        self._provider_check_pending = False
        self.notify(message, severity="error")

    def action_toggle_question_mode(self) -> None:
        modes = list(QuestionMode)
        current_index = modes.index(self.current_question_mode)
        self.current_question_mode = modes[(current_index + 1) % len(modes)]
        self.notify(f"Next question mode: {MODE_LABELS[self.current_question_mode]}", severity="information")

    def load_new_session(self) -> None:
        self._generation_id += 1
        generation_id = self._generation_id
        provider = self.current_provider
        mode = self.current_question_mode
        self.active_session = None
        self.answer_submitted = False

        self.query_one("#interaction-area").add_class("hidden")
        self.query_one("#feedback-container").add_class("hidden")
        self.query_one("#question-box", Static).update("Generating question...")
        self.query_one("#main-status", Label).remove_class("hidden")
        self.query_one("#main-status", Label).update(f"Generating {MODE_LABELS[mode]} question...")
        answer_options = self.query_one("#answer-options", OptionList)
        answer_options.set_options([])
        answer_options.disabled = False
        self.query_one("#btn-next").add_class("hidden")
        self.query_one("#model-answer-label").add_class("hidden")
        self.query_one("#model-answer-content").add_class("hidden")

        self.generate_question(generation_id, provider, mode)

    @work(exclusive=True, group="generation", exit_on_error=False)
    async def generate_question(self, generation_id: int, provider: Provider, mode: QuestionMode) -> None:
        try:
            session = await self.question_service.generate(provider, mode)
        except CodeRecallError as error:
            self._show_generation_error(generation_id, str(error))
            return
        except Exception:
            logger.exception("Unexpected question generation failure")
            self._show_generation_error(
                generation_id,
                "Unexpected generation failure. Check the application log.",
            )
            return

        self._show_question(generation_id, session)

    def _show_question(self, generation_id: int, session: QuestionSession) -> None:
        if generation_id != self._generation_id:
            return
        self.active_session = session
        self.query_one("#main-status", Label).add_class("hidden")
        self.query_one("#question-box", Static).update(Markdown(f"**Question:**\n{session.question}"))
        answer_options = self.query_one("#answer-options", OptionList)
        answer_options.set_options([f"{chr(65 + index)}. {answer}" for index, answer in enumerate(session.answers)])
        answer_options.highlighted = 0
        provider_name = "OpenAI" if session.provider is Provider.OPENAI else "Ollama"
        model_name = (
            self.settings.OPENAI_MODEL_NAME if session.provider is Provider.OPENAI else self.settings.MODEL_NAME
        )
        self.query_one("#source-label", Label).update(
            f"Source: {session.source_title}  |  Provider: {provider_name}  |  Model: {model_name}"
        )
        self.query_one("#interaction-area").remove_class("hidden")
        answer_options.focus()

    def _show_generation_error(self, generation_id: int, error: str) -> None:
        if generation_id != self._generation_id:
            return
        self.query_one("#main-status", Label).update("Question generation failed")
        self.query_one("#question-box", Static).update(f"Error: {error}")
        self.query_one("#source-label", Label).update("")
        self.query_one("#interaction-area").remove_class("hidden")
        self.query_one("#btn-next").remove_class("hidden")
        self.query_one("#btn-next", Button).focus()

    @on(OptionList.OptionSelected, "#answer-options")
    def select_answer(self, event: OptionList.OptionSelected) -> None:
        session = self.active_session
        if self.answer_submitted or session is None or event.option_index >= len(session.answers):
            return

        self.answer_submitted = True
        selected_index = event.option_index
        selected_answer = session.answers[selected_index]
        is_correct = selected_index == session.correct_index

        answer_options = event.option_list
        correct_answer = session.answers[session.correct_index]
        answer_options.replace_option_prompt_at_index(
            session.correct_index,
            f"{chr(65 + session.correct_index)}. {correct_answer} [CORRECT]",
        )
        if not is_correct:
            answer_options.replace_option_prompt_at_index(
                selected_index,
                f"{chr(65 + selected_index)}. {selected_answer} [YOUR CHOICE]",
            )
        answer_options.disabled = True
        self._display_feedback(session, selected_answer, is_correct)

    def _display_feedback(self, session: QuestionSession, selected_answer: str, is_correct: bool) -> None:
        self.query_one("#main-status", Label).add_class("hidden")
        status_label = self.query_one("#feedback-status", Label)
        status_label.update("Correct" if is_correct else "Incorrect")
        status_label.remove_class("correct", "incorrect")
        status_label.add_class("correct" if is_correct else "incorrect")
        self.query_one("#feedback-content", Static).update(
            Markdown(f"**Your answer:** {selected_answer}\n\n{session.explanation}")
        )
        self.query_one("#model-answer-label").remove_class("hidden")
        answer_content = self.query_one("#model-answer-content", Static)
        answer_content.remove_class("hidden")
        answer_content.update(Markdown(session.answers[session.correct_index]))
        self.query_one("#feedback-container").remove_class("hidden")
        self.query_one("#btn-next").remove_class("hidden")
        self.query_one("#btn-next", Button).focus()

    @on(Button.Pressed, "#btn-next")
    def action_next_question(self) -> None:
        if self.query_one("#btn-next").has_class("hidden"):
            return
        self.load_new_session()

    @on(Button.Pressed, "#btn-quit")
    def quit_app(self) -> None:
        self.exit()
