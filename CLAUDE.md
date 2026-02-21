# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CodeRecall is a terminal-based flashcard application that uses local LLMs (via Ollama) to generate questions from markdown articles and evaluate user answers. Built with Textual for the TUI and Pydantic for configuration.

## Commands

```bash
# Install dependencies
uv sync

# Run the application
uv run main.py

# Run via cron scheduler script
./recall.sh
```

**Prerequisites:** Ollama must be installed and running. The app will auto-pull the `gemma2:2b` model if not present.

## Architecture

### Main Components

- **`main.py`** - Application entry point containing:
  - `StartupScreen` - Handles initialization, Ollama service/model checks
  - `CodeRecallApp` - Main Textual app with question generation, answer evaluation, and UI
  - `EvaluationResponse` - Pydantic model for structured LLM evaluation output

- **`settings.py`** - Pydantic BaseSettings for environment configuration (`MODEL_NAME`, `ARTICLES_DIR`)

- **`recall.sh`** - Cron automation script that sets up GUI environment variables and launches the app in a terminal window

### Application Flow

1. StartupScreen verifies Ollama service → checks model availability → validates articles directory
2. Random markdown article selected → LLM generates conceptual question (JSON format)
3. User types answer in TUI → LLM evaluates as PASS/FAIL with explanation
4. On exit, model is explicitly unloaded to free VRAM

### Key Bindings

- `Ctrl+Q` - Quit
- `Ctrl+S` - Submit Answer
- `Ctrl+N` - Next Question

## Configuration

Environment variables in `.env` (see `.env.example`):
- `ARTICLES_DIR` - Directory containing markdown articles (default: `./articles`)
- `MODEL_NAME` - Ollama model to use (default: `gemma2:2b`)
- `DISPLAY`, `XAUTHORITY`, `DBUS_SESSION_BUS_ADDRESS` - For cron GUI integration

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
