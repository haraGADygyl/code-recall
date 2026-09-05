# 🧠 CodeRecall

CodeRecall is a lightweight, terminal-based flashcard app that uses OpenAI or local LLMs to create multiple-choice questions from curated technical topics.

## 🚀 Features

- **TUI Power**: A sleek terminal interface built with [Textual](https://textual.textualize.io/).
- **Dual LLM Support**: Choose between [OpenAI](https://openai.com/) (default) or local [Ollama](https://ollama.ai/) models. Switch providers on-the-fly with `Ctrl+T`.
- **Stay Focused**: Designed to be triggered by an OS scheduler (like Cron) to keep your recall sessions consistent.
- **Quick Recall**: Choose from four plausible answers, then press `Enter` or click Submit for an immediate explanation.
- **Balanced Catalogs**: Advanced Python and System Design each draw from 88 senior-level topics across 11 categories, selecting a category before a topic.
- **Advanced Python On Demand**: Every Python question is generated from the catalog at request time, so no article library has to be maintained.
- **No Giveaway Answers**: Answer length is enforced, not just requested, so the correct option cannot be spotted by being the longest.
- **VRAM Optimized**: Ollama questions unload the configured model after generation by default.

## 🛠 Setup

### 1. Prerequisites
- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** (Python package manager)
- **[OpenAI API Key](https://platform.openai.com/)** (for OpenAI provider) OR
- **[Ollama](https://ollama.ai/)** (for local models, installed and available in PATH)
- **GNOME Terminal, systemd, and `flock`** (only for scheduled desktop launches through `recall.sh`)

### 2. Installation
Clone this repository and sync dependencies:

```bash
uv sync
```

For development tools and tests:

```bash
uv sync --extra dev
```

### 3. Configuration
Copy the example environment file and customize it if needed:

```bash
cp .env.example .env
```

Open `.env` and adjust the variables:
- `DEFAULT_PROVIDER`: LLM provider to use - `openai` (default) or `ollama`.
- `OPENAI_API_KEY`: Your OpenAI API key (required for OpenAI provider).
- `OPENAI_MODEL_NAME`: The OpenAI model to use (defaults to `gpt-4.1-mini`).
- `MODEL_NAME`: The Ollama model to use (defaults to `gemma2:2b`).
- `DEFAULT_QUESTION_MODE`: Initial mode (`advanced-python`, `rest-api`, `fastapi`, or `system-design`).
- `ANSWER_BALANCE_ATTEMPTS`: Attempts allowed to stop the correct answer from being the longest option (defaults to `2`; `1` disables regeneration).

Restrict the local settings file because it contains credentials:

```bash
chmod 600 .env
```

## 🎮 Usage

Run the app directly with `uv`:

```bash
uv run main.py
```

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `Up` / `Down` | Select Answer |
| `Enter` | Submit Answer |
| `Ctrl+N` | Next Question |
| `Ctrl+T` | Toggle Provider |
| `Ctrl+R` | Toggle Question Mode |
| `Ctrl+Q` | Quit Application |

## ⚙️ How it Works

1. **Generation**: The app selects a technical topic and asks the LLM for one question, one correct answer, three distractors, and a rationale.
2. **Interaction**: Use the arrow keys to highlight an answer, then press `Enter` or click Submit.
3. **Evaluation**: The app checks the selected answer locally and immediately shows the correct answer and rationale.
4. **Switch Providers**: Press `Ctrl+T` anytime to toggle between OpenAI and Ollama. The question's provider is shown below its answers.

Advanced Python and System Design questions use categorized catalogs. Each question independently selects one of 11 categories and then one of its 8 topics, keeping broad areas evenly represented without storing topic history. Question modes are entirely topic-driven, so nothing is read from disk beyond the shipped catalogs.

### Answer Length Parity

Models write correct answers precisely and distractors tersely, which makes the correct option guessable from its length alone. Asking for parity in the prompt is not enough on its own, so every generated question is measured: if the correct answer exceeds the longest distractor by more than 15% (with a 10-character floor so terse answers such as `PUT` versus `POST` are never penalized), the question is regenerated with explicit corrective feedback. The feedback matters because Ollama generates at temperature zero and an identical retry would return an identical question. Length parity is a quality concern rather than a validity one, so exhausting `ANSWER_BALANCE_ATTEMPTS` returns the most balanced candidate instead of showing an error.

## Architecture

Application code is split by responsibility under `code_recall/`:

- `app.py`: Textual UI with exclusive workers and stale-result rejection
- `config.py`: Settings, paths, and state-directory configuration
- `content.py`: Typed topic catalog loading
- `domain.py`: Typed providers, modes, questions, and sessions
- `providers.py`: OpenAI and Ollama adapters
- `questions.py`: Prompt construction and question orchestration

## 💬 Commit Convention

This project enforces [Conventional Commits](https://www.conventionalcommits.org/) with a **required scope** via a `commit-msg` pre-commit hook. All commit messages must follow the format:

```
type(scope): description
```

Install the hook after cloning:

```bash
uv run pre-commit install --hook-type commit-msg
```

## 📝 Automation (Cron)

To run CodeRecall every hour and have it pop up a terminal window:

1.  Make sure `recall.sh` has the correct paths.
2.  Open your crontab:
    ```bash
    crontab -e
    ```
3.  Add the following line (update the path to the script):
    ```bash
    0 * * * * /home/manushev/GitHub/python/code-recall/recall.sh
    ```

> [!NOTE]
> The `recall.sh` script reads the active graphical session environment from the user systemd manager so Cron can open GNOME Terminal on the current desktop. Only one session may run at a time; later invocations are skipped while a window remains open. Launcher errors are written to `${XDG_STATE_HOME:-~/.local/state}/code-recall/recall-error.log`.

---
Created by [Tihomir Manushev](https://github.com/haraGADygyl).
