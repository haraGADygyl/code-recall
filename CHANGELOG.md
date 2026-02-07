# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.2] - 2026-02-07

### Added

- REST API Design question mode with toggle (`Ctrl+R`) between articles and REST API topics
- `DEFAULT_QUESTION_MODE` setting to configure startup mode (`articles` or `rest-api`)
- REST API questions covering HTTP methods, status codes, versioning, auth patterns, and more

### Changed

- Articles directory check at startup only runs in articles mode

## [0.1.1] - 2026-02-03

### Added

- Commit-msg pre-commit hook using `conventional-pre-commit` to enforce `type(scope): description` format

## [0.1.0] - 2026-01-17

### Added

- Terminal-based flashcard application using Textual TUI
- Question generation from markdown articles via Ollama (local LLM)
- Answer evaluation with PASS/FAIL feedback and explanations
- OpenAI provider integration with environment-variable-based provider switching
- Cron automation script (`recall.sh`) for scheduled sessions
- Pydantic-based configuration with `.env` support
- Pre-commit hooks with Ruff linter and mypy type checking
