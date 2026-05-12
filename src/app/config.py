from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from typing import Any

from app.domain.errors import ConfigError
from app.domain.models import CourseConfig


@dataclass(frozen=True)
class PortalSettings:
    login_url: str
    registration_url: str
    expected_registration_page_text: str = ""
    login_username_field: str = "username"
    login_password_field: str = "password"
    login_event_target: str = ""
    login_multipart: bool = True
    registration_action: str = "addMonDangKy"
    registration_course_field: str = "data"
    registration_multipart: bool = True


@dataclass(frozen=True)
class StudentSettings:
    username_env: str = "PORTAL_USERNAME"
    password_env: str = "PORTAL_PASSWORD"
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)


@dataclass(frozen=True)
class RuntimeSettings:
    mode: str = "auto"
    dry_run: bool = True
    relogin_after_seconds: int = 600
    request_timeout_seconds: int = 15
    normal_interval_seconds: int = 30
    hot_interval_seconds: int = 3
    max_requests_per_minute: int = 20
    stop_when_all_success: bool = True
    max_failures_before_notify: int = 5


@dataclass(frozen=True)
class NotificationSettings:
    telegram_enabled: bool = False
    telegram_bot_token_env: str = "TELEGRAM_BOT_TOKEN"
    telegram_chat_id_env: str = "TELEGRAM_CHAT_ID"
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id: str = field(default="", repr=False)


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = "sqlite:///data/app.db"


@dataclass(frozen=True)
class Settings:
    portal: PortalSettings
    student: StudentSettings
    runtime: RuntimeSettings
    courses: tuple[CourseConfig, ...]
    notification: NotificationSettings = field(default_factory=NotificationSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        os.environ.setdefault(key, value)


def load_settings(
    path: str | Path = "config.yaml",
    *,
    env_path: str | Path = ".env",
    require_secrets: bool = True,
) -> Settings:
    load_dotenv(env_path)
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    raw = _load_mapping(config_path)
    return build_settings(raw, require_secrets=require_secrets)


def build_settings(raw: dict[str, Any], *, require_secrets: bool = True) -> Settings:
    portal_raw = _section(raw, "portal")
    runtime_raw = raw.get("runtime", {}) or {}
    student_raw = raw.get("student", {}) or {}
    notification_raw = raw.get("notification", {}) or {}
    database_raw = raw.get("database", {}) or {}

    courses_raw = raw.get("courses")
    if not isinstance(courses_raw, list) or not courses_raw:
        raise ConfigError("At least one course must be configured")

    portal = PortalSettings(
        login_url=_required_str(portal_raw, "login_url"),
        registration_url=_required_str(portal_raw, "registration_url"),
        expected_registration_page_text=str(
            portal_raw.get("expected_registration_page_text", "")
        ),
        login_username_field=str(portal_raw.get("login_username_field", "username")),
        login_password_field=str(portal_raw.get("login_password_field", "password")),
        login_event_target=str(portal_raw.get("login_event_target", "")),
        login_multipart=bool(portal_raw.get("login_multipart", True)),
        registration_action=str(portal_raw.get("registration_action", "addMonDangKy")),
        registration_course_field=str(portal_raw.get("registration_course_field", "data")),
        registration_multipart=bool(portal_raw.get("registration_multipart", True)),
    )

    username_env = str(student_raw.get("username_env", "PORTAL_USERNAME"))
    password_env = str(student_raw.get("password_env", "PORTAL_PASSWORD"))
    username = os.environ.get(username_env, "")
    password = os.environ.get(password_env, "")
    if require_secrets and (not username or not password):
        raise ConfigError(
            f"Missing portal credentials. Set {username_env} and {password_env}."
        )
    student = StudentSettings(
        username_env=username_env,
        password_env=password_env,
        username=username,
        password=password,
    )

    runtime = RuntimeSettings(
        mode=str(runtime_raw.get("mode", "auto")),
        dry_run=bool(runtime_raw.get("dry_run", True)),
        relogin_after_seconds=int(runtime_raw.get("relogin_after_seconds", 600)),
        request_timeout_seconds=int(runtime_raw.get("request_timeout_seconds", 15)),
        normal_interval_seconds=int(runtime_raw.get("normal_interval_seconds", 30)),
        hot_interval_seconds=int(runtime_raw.get("hot_interval_seconds", 3)),
        max_requests_per_minute=int(runtime_raw.get("max_requests_per_minute", 20)),
        stop_when_all_success=bool(runtime_raw.get("stop_when_all_success", True)),
        max_failures_before_notify=int(runtime_raw.get("max_failures_before_notify", 5)),
    )

    courses = tuple(_course_from_raw(item) for item in courses_raw)

    token_env = str(notification_raw.get("telegram_bot_token_env", "TELEGRAM_BOT_TOKEN"))
    chat_env = str(notification_raw.get("telegram_chat_id_env", "TELEGRAM_CHAT_ID"))
    notification = NotificationSettings(
        telegram_enabled=bool(notification_raw.get("telegram_enabled", False)),
        telegram_bot_token_env=token_env,
        telegram_chat_id_env=chat_env,
        telegram_bot_token=os.environ.get(token_env, ""),
        telegram_chat_id=os.environ.get(chat_env, ""),
    )

    database = DatabaseSettings(url=str(database_raw.get("url", "sqlite:///data/app.db")))
    return Settings(
        portal=portal,
        student=student,
        runtime=runtime,
        courses=courses,
        notification=notification,
        database=database,
    )


def sqlite_path_from_url(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ConfigError("Only sqlite:/// database URLs are supported by this MVP")
    return Path(url.removeprefix(prefix))


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        import json

        parsed = json.loads(text)
    else:
        parsed = _load_yaml(text)
    if not isinstance(parsed, dict):
        raise ConfigError("Config root must be a mapping")
    return parsed


def _load_yaml(text: str) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _parse_simple_yaml(text)
    return yaml.safe_load(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    lines = []
    for raw in text.splitlines():
        without_comment = _remove_comment(raw.rstrip())
        if without_comment.strip():
            lines.append((len(without_comment) - len(without_comment.lstrip(" ")), without_comment.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for index, (indent, content) in enumerate(lines):
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        next_line = lines[index + 1] if index + 1 < len(lines) else None

        if content.startswith("- "):
            if not isinstance(parent, list):
                raise ConfigError(f"Unexpected list item: {content}")
            value_text = content[2:].strip()
            if ":" in value_text and not value_text.startswith(("'", '"')):
                key, value = _split_key_value(value_text)
                item: dict[str, Any] = {}
                if value == "":
                    container: Any = _new_container(next_line, indent)
                    item[key] = container
                    parent.append(item)
                    stack.append((indent, item))
                    stack.append((indent + 1, container))
                else:
                    item[key] = _parse_scalar(value)
                    parent.append(item)
                    stack.append((indent, item))
            else:
                parent.append(_parse_scalar(value_text))
            continue

        key, value = _split_key_value(content)
        if not isinstance(parent, dict):
            raise ConfigError(f"Expected mapping before: {content}")
        if value == "":
            container = _new_container(next_line, indent)
            parent[key] = container
            stack.append((indent, container))
        else:
            parent[key] = _parse_scalar(value)

    return root


def _new_container(next_line: tuple[int, str] | None, current_indent: int) -> dict[str, Any] | list[Any]:
    if next_line and next_line[0] > current_indent and next_line[1].startswith("- "):
        return []
    return {}


def _split_key_value(content: str) -> tuple[str, str]:
    if ":" not in content:
        raise ConfigError(f"Expected key: value line, got: {content}")
    key, value = content.split(":", 1)
    key = key.strip()
    if not key:
        raise ConfigError(f"Empty config key in line: {content}")
    return key, value.strip()


def _parse_scalar(value: str) -> Any:
    value = _strip_quotes(value.strip())
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _remove_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing config section: {name}")
    return value


def _required_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing required config value: {key}")
    return value


def _course_from_raw(raw: Any) -> CourseConfig:
    if not isinstance(raw, dict):
        raise ConfigError("Each course must be a mapping")
    course_id = str(raw.get("id", "")).strip()
    if not course_id:
        raise ConfigError("Course id is required")
    return CourseConfig(
        id=course_id,
        name=str(raw.get("name", course_id)),
        priority=int(raw.get("priority", 100)),
        enabled=bool(raw.get("enabled", True)),
    )
