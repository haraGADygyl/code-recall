import json
import logging
import random
import subprocess
import time
from typing import Any, Self, TypeVar, cast

import ollama
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator
from rich.markdown import Markdown
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Label,
    LoadingIndicator,
    OptionList,
    Static,
)

from settings import settings

logging.basicConfig(filename="debug.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class MultipleChoiceQuestion(BaseModel):
    question: str = Field(..., description="A concise technical question")
    correct_answer: str = Field(..., description="The single correct answer")
    distractors: list[str] = Field(..., min_length=3, max_length=3, description="Three plausible wrong answers")
    explanation: str = Field(
        ...,
        description="A concise explanation of why the correct answer is correct",
    )

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        """Normalize generated content and require four distinct answers."""
        self.question = self.question.strip()
        self.correct_answer = self.correct_answer.strip()
        self.distractors = [answer.strip() for answer in self.distractors]
        self.explanation = self.explanation.strip()

        if not self.question or not self.explanation or any(not answer for answer in self.all_answers):
            raise ValueError("Question, answers, and explanation must not be blank")

        normalized_answers = [answer.casefold() for answer in self.all_answers]
        if len(set(normalized_answers)) != 4:
            raise ValueError("The correct answer and distractors must be unique")

        return self

    @property
    def all_answers(self) -> list[str]:
        return [self.correct_answer, *self.distractors]


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class StartupScreen(Screen[None]):
    """Screen for checking dependencies."""

    status_message = reactive("Initializing...")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("CodeRecall Setup", id="startup-title"),
            LoadingIndicator(),
            Label("", id="status-label"),
            id="startup-container",
        )

    def on_mount(self) -> None:
        self.query_one("#status-label", Label).update(self.status_message)
        self.run_startup_checks()

    @work(thread=True)
    def run_startup_checks(self) -> None:
        """Run startup checks based on the default provider."""
        # Only check Ollama if it's the default provider
        if settings.DEFAULT_PROVIDER == "ollama" and not self.check_ollama():
            return

        # Check Articles (only required in articles mode)
        if settings.DEFAULT_QUESTION_MODE == "articles":
            logging.info("Startup: Checking articles...")
            self.update_status("Checking articles...")
            if not settings.ARTICLES_DIR.exists() or not list(settings.ARTICLES_DIR.glob("*.md")):
                logging.error("Startup: No articles found.")
                self.fail_startup(f"No .md files found in {settings.ARTICLES_DIR.absolute()}")
                return

        logging.info("Startup: Complete.")
        self.update_status("Ready!")
        time.sleep(1)
        self.app.call_from_thread(self.finish_startup)

    def check_ollama(self) -> bool:
        """Check Ollama service and model. Returns True if successful."""
        logging.info("Startup: Checking Ollama service...")
        self.update_status("Checking Ollama service...")
        try:
            ollama.list()
            logging.info("Startup: Ollama service is running.")
        except Exception as e:
            logging.warning(f"Startup: Ollama not running ({e}). Attempting to start...")
            self.update_status("Ollama not running. Attempting to start...")
            try:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logging.info("Startup: Launched ollama serve.")
                for i in range(10):
                    time.sleep(1)
                    try:
                        ollama.list()
                        logging.info("Startup: Ollama connected successfully.")
                        break
                    except Exception:
                        logging.debug(f"Startup: Waiting for Ollama... {i}")
                else:
                    logging.error("Startup: Timeout starting Ollama.")
                    self.fail_startup("Could not start Ollama. Please run 'ollama serve' manually.")
                    return False
            except FileNotFoundError:
                logging.error("Startup: Ollama binary not found.")
                self.fail_startup("Ollama executable not found. Please install Ollama.")
                return False

        # Check for Model
        logging.info(f"Startup: Checking for model {settings.MODEL_NAME}...")
        self.update_status(f"Checking for model {settings.MODEL_NAME}...")
        try:
            models = ollama.list()
            model_names = [m["model"] for m in models.get("models", [])]
            logging.info(f"Startup: Found models: {model_names}")
            if not any(settings.MODEL_NAME in name for name in model_names):
                logging.info(f"Startup: {settings.MODEL_NAME} not found. Pulling...")
                self.update_status(f"Model {settings.MODEL_NAME} not found. Pulling (this may take a while)...")
                ollama.pull(settings.MODEL_NAME)
                logging.info("Startup: Pull complete.")
        except Exception as e:
            logging.error(f"Startup: Model check failed: {e}")
            self.fail_startup(f"Error checking/pulling model: {e}")
            return False

        return True

    def finish_startup(self) -> None:
        logging.info("Startup: Finishing startup sequence...")
        self.app.pop_screen()
        cast("CodeRecallApp", self.app).load_new_session()

    def update_status(self, msg: str) -> None:
        self.status_message = msg
        try:
            self.app.call_from_thread(lambda: self.query_one("#status-label", Label).update(msg))
        except Exception as e:
            logging.error(f"Error updating status: {e}")

    def fail_startup(self, msg: str) -> None:
        self.update_status(f"ERROR: {msg}")
        logging.error(f"Startup failed: {msg}")


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
    
    #question-title {
        color: #00ff00;
        text-style: bold;
    }

    #source-label {
        width: 100%;
        color: #666;
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

    MODE_LABELS: dict[str, str] = {
        "articles": "Articles",
        "rest-api": "REST API Design",
        "fastapi": "FastAPI",
        "system-design": "System Design",
    }

    TOPIC_FILES: dict[str, str] = {
        "rest-api": "REST_API_TOPICS_FILE",
        "fastapi": "FASTAPI_TOPICS_FILE",
        "system-design": "SYSTEM_DESIGN_TOPICS_FILE",
    }

    current_article_text: str = ""
    current_article_title: str = ""
    current_question: str = ""
    current_answers: list[str] = []
    current_correct_index: int = -1
    current_explanation: str = ""
    answer_submitted: bool = False
    question_provider: str = settings.DEFAULT_PROVIDER
    question_mode: str = settings.DEFAULT_QUESTION_MODE
    current_provider: reactive[str] = reactive(settings.DEFAULT_PROVIDER)
    current_question_mode: reactive[str] = reactive(settings.DEFAULT_QUESTION_MODE)
    ollama_verified: bool = False

    class StartupComplete(Message):
        pass

    def compose(self) -> ComposeResult:
        # Main structure, initially hidden or empty until startup passes
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
        # Set initial provider from settings and mark Ollama as verified if it was default
        self.current_provider = settings.DEFAULT_PROVIDER
        if settings.DEFAULT_PROVIDER == "ollama":
            self.ollama_verified = True
        self.push_screen(StartupScreen())

    def watch_current_provider(self, provider: str) -> None:
        """Update UI when provider changes."""
        self.update_provider_display()

    def update_provider_display(self) -> None:
        """Update the provider status in the source label."""
        provider_name = "OpenAI" if self.question_provider == "openai" else "Ollama"
        model_name = settings.OPENAI_MODEL_NAME if self.question_provider == "openai" else settings.MODEL_NAME
        mode_label = self.MODE_LABELS.get(self.question_mode, self.current_article_title)
        try:
            source_label = self.query_one("#source-label", Label)
            source_label.update(f"Source: {mode_label}  |  Provider: {provider_name}  |  Model: {model_name}")
        except Exception as e:
            logging.error(f"Failed to update provider display: {e}")

    def action_toggle_provider(self) -> None:
        """Toggle between OpenAI and Ollama providers."""
        if self.current_provider == "openai":
            # Switching to Ollama - need to verify it's available
            if not self.ollama_verified:
                self.notify("Checking Ollama availability...", severity="information")
                self.verify_and_switch_to_ollama()
            else:
                self.current_provider = "ollama"
                self.update_provider_display()
                self.notify("Switched to Ollama", severity="information")
        else:
            self.current_provider = "openai"
            self.update_provider_display()
            self.notify("Switched to OpenAI", severity="information")

    def action_toggle_question_mode(self) -> None:
        """Cycle between Articles, REST API Design, FastAPI, and System Design question modes."""
        modes = list(self.MODE_LABELS)
        current_idx = modes.index(self.current_question_mode)
        self.current_question_mode = modes[(current_idx + 1) % len(modes)]
        self.notify(f"Switched to {self.MODE_LABELS[self.current_question_mode]} mode", severity="information")

    def watch_current_question_mode(self, mode: str) -> None:
        """Update UI when question mode changes."""
        self.update_provider_display()

    @work(thread=True)
    def verify_and_switch_to_ollama(self) -> None:
        """Verify Ollama is available before switching."""
        try:
            ollama.list()
            # Check if model exists
            models = ollama.list()
            model_names = [m["model"] for m in models.get("models", [])]
            if not any(settings.MODEL_NAME in name for name in model_names):
                self.call_from_thread(
                    lambda: self.notify(
                        f"Model {settings.MODEL_NAME} not found. Please pull it first.", severity="error"
                    )
                )
                return
            self.ollama_verified = True
            self.current_provider = "ollama"
            self.call_from_thread(self._on_ollama_switch_complete)
        except Exception as e:
            logging.error(f"Ollama verification failed: {e}")
            self.call_from_thread(
                lambda: self.notify("Ollama not available. Please start Ollama service.", severity="error")
            )

    def _on_ollama_switch_complete(self) -> None:
        """Called from main thread after successful Ollama switch."""
        self.update_provider_display()
        self.notify("Switched to Ollama", severity="information")

    def llm_chat(
        self,
        messages: list[dict[str, str]],
        response_model: type[ResponseModel],
        provider: str | None = None,
    ) -> ResponseModel:
        """Request and validate a structured response from the current provider."""
        selected_provider = provider or self.current_provider
        if selected_provider == "openai":
            return self._openai_chat(messages, response_model)
        return self._ollama_chat(messages, response_model)

    def _openai_chat(self, messages: list[dict[str, str]], response_model: type[ResponseModel]) -> ResponseModel:
        """Request a parsed structured response from OpenAI."""
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        kwargs: dict[str, Any] = {
            "model": settings.OPENAI_MODEL_NAME,
            "messages": messages,
            "response_format": response_model,
        }
        response = client.chat.completions.parse(**kwargs)
        message = response.choices[0].message
        parsed: ResponseModel | None = message.parsed
        if parsed is not None:
            return parsed
        if message.refusal:
            raise ValueError(f"OpenAI refused the question request: {message.refusal}")
        raise ValueError("OpenAI returned no structured question")

    def _ollama_chat(self, messages: list[dict[str, str]], response_model: type[ResponseModel]) -> ResponseModel:
        """Request and validate a structured response from Ollama."""
        kwargs: dict[str, Any] = {
            "model": settings.MODEL_NAME,
            "messages": messages,
            "format": response_model.model_json_schema(),
        }
        response = ollama.chat(**kwargs)
        return response_model.model_validate_json(str(response["message"]["content"]))

    def on_startup_complete(self, message: StartupComplete) -> None:
        self.pop_screen()
        self.load_new_session()

    def load_new_session(self) -> None:
        """Pick a random article and start generation."""
        question_mode = self.current_question_mode
        question_provider = self.current_provider

        # Reset UI
        self.answer_submitted = False
        self.current_answers = []
        self.current_correct_index = -1
        self.current_explanation = ""
        self.query_one("#interaction-area").add_class("hidden")
        self.query_one("#feedback-container").add_class("hidden")
        self.query_one("#question-box", Static).update("Generating question...")
        self.query_one("#main-status", Label).remove_class("hidden")
        answer_options = self.query_one("#answer-options", OptionList)
        answer_options.set_options([])
        answer_options.disabled = False
        self.query_one("#btn-next").add_class("hidden")
        self.query_one("#model-answer-label").add_class("hidden")
        self.query_one("#model-answer-content").add_class("hidden")

        if question_mode == "articles":
            self.query_one("#main-status", Label).update("Selecting article and generating question...")
            files = list(settings.ARTICLES_DIR.glob("*.md"))
            if not files:
                self.notify("No articles found", severity="error")
                self.show_generation_error("No articles found")
                return
            selected_file = random.choice(files)
            self.current_article_title = selected_file.name
            self.current_article_text = selected_file.read_text(encoding="utf-8")
        else:
            label = self.MODE_LABELS[question_mode]
            self.query_one("#main-status", Label).update(f"Generating {label} question...")
            self.current_article_title = label
            self.current_article_text = ""

        self.generate_question(question_mode, question_provider, self.current_article_text)

    @work(thread=True)
    def generate_question(self, question_mode: str, question_provider: str, article_text: str) -> None:
        try:
            topic_file_attr = self.TOPIC_FILES.get(question_mode)
            if topic_file_attr:
                topics_file = getattr(settings, topic_file_attr)
                topics = json.loads(topics_file.read_text(encoding="utf-8"))
                topic = random.choice(topics)
                mode_label = self.MODE_LABELS[question_mode]
                user_prompt = (
                    f"Generate one concise conceptual multiple-choice question about this {mode_label} topic: {topic}."
                )
            else:
                user_prompt = (
                    f"Read the following text:\n\n{article_text}\n\n"
                    "Generate one concise conceptual Python 3 multiple-choice question based only on this text."
                )

            question = self.llm_chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You create technical multiple-choice questions. Each question must have one "
                            "unambiguously correct answer and exactly three plausible but incorrect distractors. "
                            "Keep the question brief, avoid code-writing tasks and trick questions, and never use "
                            "'all of the above' or 'none of the above'. Keep all answers similar in length and style. "
                            "Explain briefly why the correct answer is correct."
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                response_model=MultipleChoiceQuestion,
                provider=question_provider,
            )
            answers = question.all_answers
            random.shuffle(answers)

            self.current_question = question.question
            self.current_answers = answers
            self.current_correct_index = answers.index(question.correct_answer)
            self.current_explanation = question.explanation
            self.question_mode = question_mode
            self.question_provider = question_provider

            # Update UI
            self.call_from_thread(self.show_question)

        except Exception as e:
            logging.error(f"Generation error: {e}")
            self.call_from_thread(self.show_generation_error, str(e))

    def show_question(self) -> None:
        self.query_one("#main-status", Label).add_class("hidden")
        q_box = self.query_one("#question-box", Static)
        q_box.update(Markdown(f"**Question:**\n{self.current_question}"))
        answer_options = self.query_one("#answer-options", OptionList)
        answer_options.set_options(
            [f"{chr(65 + index)}. {answer}" for index, answer in enumerate(self.current_answers)]
        )
        answer_options.highlighted = 0
        self.update_provider_display()

        self.query_one("#interaction-area").remove_class("hidden")
        answer_options.focus()

    def show_generation_error(self, error: str) -> None:
        self.query_one("#main-status", Label).update("Question generation failed")
        self.query_one("#question-box", Static).update(f"Error: {error}")
        self.query_one("#interaction-area").remove_class("hidden")
        self.query_one("#btn-next").remove_class("hidden")
        self.query_one("#btn-next").focus()

    @on(OptionList.OptionSelected, "#answer-options")
    def select_answer(self, event: OptionList.OptionSelected) -> None:
        if self.answer_submitted or event.option_index >= len(self.current_answers):
            return

        self.answer_submitted = True
        answer_options = event.option_list
        selected_index = event.option_index
        selected_answer = self.current_answers[selected_index]
        is_correct = selected_index == self.current_correct_index

        correct_marker = " [CORRECT]"
        correct_answer = self.current_answers[self.current_correct_index]
        answer_options.replace_option_prompt_at_index(
            self.current_correct_index,
            f"{chr(65 + self.current_correct_index)}. {correct_answer}{correct_marker}",
        )
        if not is_correct:
            answer_options.replace_option_prompt_at_index(
                selected_index,
                f"{chr(65 + selected_index)}. {selected_answer} [YOUR CHOICE]",
            )
        answer_options.disabled = True

        self._display_feedback(
            status_text="Correct" if is_correct else "Incorrect",
            status_class="correct" if is_correct else "incorrect",
            selected_answer=selected_answer,
        )

    def _display_feedback(self, status_text: str, status_class: str, selected_answer: str) -> None:
        self.query_one("#main-status", Label).add_class("hidden")

        status_lbl = self.query_one("#feedback-status", Label)
        status_lbl.update(status_text)
        status_lbl.remove_class("correct", "incorrect")
        status_lbl.add_class(status_class)

        self.query_one("#feedback-content", Static).update(
            Markdown(f"**Your answer:** {selected_answer}\n\n{self.current_explanation}")
        )

        self.query_one("#model-answer-label").remove_class("hidden")
        ans_content = self.query_one("#model-answer-content", Static)
        ans_content.remove_class("hidden")
        ans_content.update(Markdown(self.current_answers[self.current_correct_index]))

        self.query_one("#feedback-container").remove_class("hidden")
        self.query_one("#btn-next").remove_class("hidden")
        self.query_one("#btn-next").focus()

    @on(Button.Pressed, "#btn-next")
    def action_next_question(self) -> None:
        # Only allow next question if the button is visible (meaning we finished the previous one)
        if self.query_one("#btn-next").has_class("hidden"):
            return
        self.load_new_session()

    @on(Button.Pressed, "#btn-quit")
    def quit_app(self) -> None:
        self.exit()


if __name__ == "__main__":
    app = CodeRecallApp()
    app.run()
