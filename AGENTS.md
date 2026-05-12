# Repository Guidelines

## Project Structure & Module Organization

This repository now contains a Python service scaffold. Keep the top-level layout predictable and update this guide when the structure changes:

- `src/app/` for application source code.
- `src/app/domain/` for typed domain models, statuses, and errors.
- `src/app/portal/` for portal client and parser code.
- `src/app/services/` for registrar, scheduler, state store, notifier, and rate limiter code.
- `tests/` for automated tests that mirror the `src/` layout.
- `config.example.yaml` and `.env.example` for safe configuration templates.

Avoid committing generated output, dependency folders, or machine-local files. Add a `.gitignore` when the first toolchain is introduced.

## Build, Test, and Development Commands

Current commands, runnable from the repository root:

- `$env:PYTHONPATH = "src"; python -m app.main init-db` initializes SQLite.
- `$env:PYTHONPATH = "src"; python -m app.main reset-db` deletes and recreates SQLite state.
- `$env:PYTHONPATH = "src"; python -m app.main dry-run` runs the flow without posting registration requests.
- `$env:PYTHONPATH = "src"; python -m app.main run-once` runs one registration pass.
- `$env:PYTHONPATH = "src"; python -m app.main run` starts the long-running service.
- `$env:PYTHONPATH = "src"; python -m app.main healthcheck` checks SQLite health.
- `$env:PYTHONPATH = "src"; python -m unittest discover -s tests` runs tests without third-party dependencies.
- `$env:PYTHONPATH = "src"; python -m compileall src tests` compiles source and tests.
- `docker compose up --build -d` runs the service in Docker after `config.yaml` and `.env` exist.

Prefer script aliases, Make targets, or task-runner commands over long one-off command lines.

## Coding Style & Naming Conventions

Follow the formatter and linter for the language used in the added codebase. Until tooling exists, keep changes simple and consistent: use clear file names, small modules, and descriptive identifiers. Use `kebab-case` for documentation files such as `api-design.md`, and follow language norms for source files, for example `snake_case.py` in Python or `PascalCase.tsx` for React components.

## Testing Guidelines

Add tests alongside the first production code. Keep test names behavior-focused, such as `test_user_can_sign_in` or `renders-empty-state.test.tsx`. Tests should be deterministic and avoid external services unless explicitly marked as integration tests. Document any coverage expectations after a test framework is selected.

## Commit & Pull Request Guidelines

This directory is not currently initialized as a Git repository, so no local commit convention is available. Use concise, imperative commit messages such as `Add login form validation` or `Fix CSV import parsing`. Pull requests should include a summary, validation steps, linked issues when relevant, and screenshots for UI changes.

## Agent-Specific Instructions

Before editing, inspect the current tree and preserve user changes. Keep edits scoped to the requested task, update this document when project tooling changes, and verify with the repository's documented commands once they exist.
