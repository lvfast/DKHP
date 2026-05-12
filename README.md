# Course Registration Automation Service

Python service for running a configurable course registration workflow with
dry-run mode, SQLite state, structured logs, rate limiting, and optional
Telegram notifications.

This MVP intentionally uses only Python standard library modules so it can be
compiled and tested before external dependencies are installed. The
`pyproject.toml` keeps the recommended dependency list for later upgrades.

## Features

- Loads portal URLs, courses, runtime settings, and database location from
  `config.yaml`.
- Reads credentials from environment variables or `.env`; credentials are not
  hardcoded.
- Parses login hidden inputs and maps registration responses to typed statuses.
- Keeps course and attempt state in SQLite.
- Supports `dry-run`, `run-once`, long-running `run`, `init-db`, `healthcheck`,
  and `test-notification` commands.
- Applies request-per-minute rate limiting.
- Sends important events to Telegram when enabled, otherwise logs them.

## Setup

```powershell
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
```

Edit `config.yaml` with class ids and portal field names if they differ from
the defaults. Edit `.env` with `PORTAL_USERNAME` and `PORTAL_PASSWORD`.

For the current DNN portal flow, the login settings normally look like:

```yaml
portal:
  login_username_field: 'dnn$ctr$Login$Login_DNN$txtUsername'
  login_password_field: 'dnn$ctr$Login$Login_DNN$txtPassword'
  login_event_target: 'dnn$ctr$Login$Login_DNN$cmdLogin'
  login_multipart: true
  registration_multipart: true
```

## Commands

Run directly from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m app.main init-db
python -m app.main reset-db
python -m app.main dry-run
python -m app.main run-once
python -m app.main run
python -m app.main healthcheck
python -m app.main test-notification
```

## Docker

```powershell
docker compose up --build -d
docker compose logs -f course-bot
```

The compose file mounts `config.yaml` read-only and stores SQLite data under
`./data`.

## Testing

With no third-party tools installed:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
python -m compileall src tests
```

If `pytest` and `ruff` are installed:

```powershell
python -m pytest
python -m ruff check .
```

## Security Notes

- Do not commit `.env`, `data/`, database files, logs, cookies, or session
  dumps.
- The service never logs the password and does not print cookies.
- Keep `runtime.dry_run: true` until login and parser behavior are verified.
- This service does not bypass CAPTCHA, queues, or portal protection.
