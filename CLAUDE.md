# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CodeRecall is a terminal-based flashcard application that uses OpenAI or local LLMs (via Ollama) to generate multiple-choice questions from markdown articles and technical topics. Built with Textual for the TUI and Pydantic for configuration.

## Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run main.py

# Run via cron scheduler script
./recall.sh
```

**Prerequisites:** Configure an OpenAI API key or install Ollama, depending on the selected provider. The app auto-pulls the configured Ollama model when Ollama is the default provider.

## Architecture

### Main Components

- **`main.py`** - Application entry point containing:
  - `StartupScreen` - Handles initialization, Ollama service/model checks
  - `CodeRecallApp` - Main Textual app with structured question generation, local answer evaluation, and UI
  - `MultipleChoiceQuestion` - Pydantic model for structured question output

- **`settings.py`** - Pydantic BaseSettings for environment configuration (`MODEL_NAME`, `ARTICLES_DIR`)

- **`recall.sh`** - Cron automation script that imports the active GUI environment and launches the app in a terminal window

### Application Flow

1. StartupScreen checks the selected provider and validates the articles directory when required
2. Random article or technical topic selected → LLM generates a question, four answers, and rationale
3. User selects an answer in the TUI → app evaluates it locally and displays the rationale
4. When launched through `recall.sh`, the configured Ollama model is unloaded after exit

### Key Bindings

- `Ctrl+Q` - Quit
- `Up` / `Down` - Select Answer
- `Enter` - Submit Answer
- `Ctrl+N` - Next Question
- `Ctrl+T` - Toggle Provider
- `Ctrl+R` - Toggle Question Mode

## Configuration

Environment variables in `.env` (see `.env.example`):
- `ARTICLES_DIR` - Directory containing markdown articles (default: `./articles`)
- `MODEL_NAME` - Ollama model to use (default: `gemma2:2b`)
- `OPENAI_API_KEY`, `OPENAI_MODEL_NAME` - OpenAI credentials and model
- `DEFAULT_PROVIDER` - Initial provider (`openai` or `ollama`)
- `DEFAULT_QUESTION_MODE` - Initial article or technical-topic mode

## Changelog

When updating `CHANGELOG.md`, never add entries under `[Unreleased]`. Always create a new patch version (e.g., `[0.1.3]`) unless a different version bump is specified.

## Git Workflow

Always push to `origin` after committing.

## Code Standards

Follow `.agent/rules/python-expert.md`:
- Python 3.12+, strict typing with PEP 604 unions (`X | None`)
- Pydantic V2 for validation/serialization
- Use `pathlib.Path` for file operations
- Standard library logging (no bare `print()`)
