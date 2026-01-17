import json
import logging
import random
import subprocess
import time
from typing import Any

import ollama
from openai import OpenAI
from pydantic import BaseModel, Field
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
    Static,
    TextArea,
)

from settings import settings

logging.basicConfig(filename="debug.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class EvaluationResponse(BaseModel):
    result: str = Field(..., description="PASS or FAIL")
    explanation: str = Field(..., description="A concise explanation of why it passed or failed.")
    answer: str = Field(
        ...,
        description="The correct answer to the question, independent of the user's response.",
    )


class StartupScreen(Screen):
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

        # Check Articles (always required)
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
        self.app.load_new_session()

    def update_status(self, msg: str) -> None:
        self.status_message = msg
        try:
            self.app.call_from_thread(lambda: self.query_one("#status-label", Label).update(msg))
        except Exception as e:
            logging.error(f"Error updating status: {e}")

    def fail_startup(self, msg: str) -> None:
        self.update_status(f"ERROR: {msg}")
        logging.error(f"Startup failed: {msg}")


class CodeRecallApp(App):
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

    .pass {
        color: #00ff00;
        text-style: bold;
    }

    .fail {
        color: #ff0000;
        text-style: bold;
    }

    TextArea {
        height: auto;
        border: solid #555;
    }

    .feedback-box {
        height: auto;
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
        ("ctrl+s", "submit_answer", "Submit"),
        ("ctrl+n", "next_question", "Next"),
        ("ctrl+t", "toggle_provider", "Toggle Provider"),
    ]

    current_article_text: str = ""
    current_article_title: str = ""
    current_question: str = ""
    current_provider: reactive[str] = reactive(settings.DEFAULT_PROVIDER)
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
                yield TextArea(id="answer-input", show_line_numbers=False)
                with Horizontal(id="button-bar"):
                    yield Button("Submit", id="btn-submit", variant="primary")
                    yield Button("Next Question", id="btn-next", classes="hidden", variant="success")
                    yield Button("Quit", id="btn-quit", variant="error")

            with Vertical(id="feedback-container", classes="hidden feedback-box"):
                yield Label("", id="feedback-status")
                yield Static("", id="feedback-content")
                yield Label("Expected Answer:", id="model-answer-label", classes="hidden")
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
        provider_name = "OpenAI" if self.current_provider == "openai" else "Ollama"
        model_name = settings.OPENAI_MODEL_NAME if self.current_provider == "openai" else settings.MODEL_NAME
        try:
            source_label = self.query_one("#source-label", Label)
            source_label.update(
                f"Source: {self.current_article_title}  |  Provider: {provider_name}  |  Model: {model_name}"
            )
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

    def llm_chat(self, messages: list[dict[str, str]], response_format: dict[str, Any] | str | None = None) -> str:
        """Route chat request to the current provider."""
        if self.current_provider == "openai":
            return self._openai_chat(messages, response_format)
        else:
            return self._ollama_chat(messages, response_format)

    def _openai_chat(self, messages: list[dict[str, str]], response_format: dict[str, Any] | str | None = None) -> str:
        """Send chat request to OpenAI."""
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        kwargs: dict[str, Any] = {
            "model": settings.OPENAI_MODEL_NAME,
            "messages": messages,
        }
        if response_format:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _ollama_chat(self, messages: list[dict[str, str]], response_format: dict[str, Any] | str | None = None) -> str:
        """Send chat request to Ollama."""
        kwargs: dict[str, Any] = {
            "model": settings.MODEL_NAME,
            "messages": messages,
        }
        if response_format:
            kwargs["format"] = response_format
        response = ollama.chat(**kwargs)
        return str(response["message"]["content"])

    def on_startup_complete(self, message: StartupComplete) -> None:
        self.pop_screen()
        self.load_new_session()

    def load_new_session(self) -> None:
        """Pick a random article and start generation."""
        # Reset UI
        self.query_one("#interaction-area").add_class("hidden")
        self.query_one("#feedback-container").add_class("hidden")
        self.query_one("#question-box", Static).update("Generating question...")
        self.query_one("#main-status", Label).update("Selecting article and generating question...")
        self.query_one("#main-status", Label).remove_class("hidden")
        self.query_one("#answer-input", TextArea).text = ""
        self.query_one("#btn-submit").remove_class("hidden")
        self.query_one("#btn-next").add_class("hidden")

        # Select File
        files = list(settings.ARTICLES_DIR.glob("*.md"))
        if not files:
            return  # Should be handled by startup check

        selected_file = random.choice(files)
        self.current_article_title = selected_file.name
        self.current_article_text = selected_file.read_text(encoding="utf-8")

        self.generate_question()

    @work(thread=True)
    def generate_question(self) -> None:
        user_prompt = (
            f"Read the following text:\n\n{self.current_article_text}\n\n"
            "Ask a single conceptual Python3 question based on this text to test understanding. "
            "Never ask for code examples or implementation details."
            'Return JSON format: {"question": "..."}'
        )

        try:
            response_text = self.llm_chat(
                messages=[{"role": "user", "content": user_prompt}],
                response_format="json",
            )
            data = json.loads(response_text)
            self.current_question = data.get("question", "Failed to parse question.")

            # Update UI
            self.call_from_thread(self.show_question)

        except Exception as e:
            logging.error(f"Generation error: {e}")
            self.call_from_thread(lambda ex=e: self.query_one("#question-box", Static).update(f"Error: {ex}"))

    def show_question(self) -> None:
        self.query_one("#main-status", Label).add_class("hidden")
        q_box = self.query_one("#question-box", Static)
        q_box.update(Markdown(f"**Question:**\n{self.current_question}"))
        provider_name = "OpenAI" if self.current_provider == "openai" else "Ollama"
        model_name = settings.OPENAI_MODEL_NAME if self.current_provider == "openai" else settings.MODEL_NAME
        self.query_one("#source-label", Label).update(
            f"Source: {self.current_article_title}  |  Provider: {provider_name}  |  Model: {model_name}"
        )

        self.query_one("#interaction-area").remove_class("hidden")
        self.query_one("#answer-input", TextArea).focus()

    @on(Button.Pressed, "#btn-submit")
    def action_submit_answer(self) -> None:
        # Check if button is visible/active to prevent double submit or invalid state
        if self.query_one("#btn-submit").has_class("hidden"):
            return

        user_answer = self.query_one("#answer-input", TextArea).text
        if not user_answer.strip():
            return

        self.query_one("#btn-submit").add_class("hidden")
        self.query_one("#main-status", Label).remove_class("hidden")
        self.query_one("#main-status", Label).update("Evaluating answer...")

        self.evaluate_answer(user_answer)

    @work(thread=True)
    def evaluate_answer(self, user_answer: str) -> None:
        sys_prompt = (
            "You are a strict technical interviewer. Evaluate the user's answer.\n"
            "Your output must be a valid JSON object with three fields:\n"
            "1. 'result': 'PASS' or 'FAIL'\n"
            "2. 'explanation': A concise explanation of why it passed or failed.\n"
            "3. 'answer': The correct answer to the question, independent of the user's response."
        )
        user_prompt = (
            f"Context: {self.current_article_text}\nQuestion: {self.current_question}\nUser Answer: {user_answer}\n\n"
        )

        try:
            # Use schema for Ollama, simple json for OpenAI
            response_format: dict[str, Any] | str = (
                dict(EvaluationResponse.model_json_schema()) if self.current_provider == "ollama" else "json"
            )
            content = self.llm_chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
            )

            evaluation = EvaluationResponse.model_validate_json(content)

            self.call_from_thread(self.show_feedback, evaluation)

        except Exception as e:
            logging.error(f"Evaluation error: {e}")
            self.call_from_thread(lambda ex=e: self.query_one("#feedback-content", Static).update(f"Error: {ex}"))

    def show_feedback(self, evaluation: EvaluationResponse) -> None:
        self.query_one("#main-status", Label).add_class("hidden")

        # Status Label
        status_lbl = self.query_one("#feedback-status", Label)
        status_lbl.update(evaluation.result)
        status_lbl.remove_class("pass", "fail")
        status_lbl.add_class("pass" if evaluation.result.upper() == "PASS" else "fail")

        # Explanation
        fb_content = self.query_one("#feedback-content", Static)
        fb_content.update(Markdown(evaluation.explanation))

        # Model Answer
        self.query_one("#model-answer-label").remove_class("hidden")
        ans_content = self.query_one("#model-answer-content", Static)
        ans_content.remove_class("hidden")
        ans_content.update(Markdown(evaluation.answer))

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
