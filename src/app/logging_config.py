from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
            "logger": record.name,
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") and key not in {"_event_data"}:
                continue
            if key == "_event_data" and isinstance(value, dict):
                payload.update(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%H:%M:%S")
        event_data = getattr(record, "_event_data", {})
        if not isinstance(event_data, dict):
            event_data = {}

        message = _human_message(record.getMessage(), event_data)
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return f"[{timestamp}] {record.levelname:<7} {message}"


def configure_logging(level: str = "INFO", *, log_format: str = "human") -> None:
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(HumanFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def event_extra(**data: Any) -> dict[str, Any]:
    return {"_event_data": data}


def _human_message(event: str, data: dict[str, Any]) -> str:
    if event == "portal_login_success":
        return f"Dang nhap portal thanh cong (HTTP {data.get('http_status', 'unknown')})."

    if event == "portal_login_failed":
        return f"Dang nhap portal that bai: {data.get('error', 'unknown error')}."

    if event == "registration_page_unavailable":
        return f"Khong truy cap duoc trang dang ky (HTTP {data.get('http_status', 'unknown')})."

    if event == "registration_page_text_missing":
        return "Da mo trang dang ky nhung khong tim thay doan text kiem tra trong config."

    if event == "dry_run_register_course":
        return (
            "Dry-run: se dang ky mon "
            f"{data.get('course_name', '')} ({data.get('course_id', '')}), "
            f"lan thu #{data.get('attempt_count', '?')}."
        )

    if event == "course_registration_attempt":
        message = (
            "Dang ky mon "
            f"{data.get('course_name', '')} ({data.get('course_id', '')}): "
            f"{data.get('status', 'unknown')} - {data.get('message', '')} "
            f"[HTTP {data.get('http_status', 'unknown')}, "
            f"{data.get('duration_ms', '?')}ms, "
            f"lan thu #{data.get('attempt_count', '?')}]."
        )
        if data.get("status") in {"unknown", "parse_error"} and data.get("response_excerpt"):
            message = f"{message} Portal response: {data['response_excerpt']}"
        return message

    if event == "notification":
        return f"Notification: {data.get('message', '')}"

    if event == "telegram_disabled":
        return f"Telegram dang tat, bo qua thong bao: {data.get('message', '')}"

    if event == "telegram_send_failed":
        return f"Gui Telegram that bai: {data.get('error') or data.get('response') or 'unknown error'}."

    if event == "service_started":
        return "Service da khoi dong."

    if event == "service_stopped":
        return "Service da dung."

    if event == "all_courses_success":
        return "Tat ca mon enabled da dang ky thanh cong."

    if event == "scheduler_sleep":
        return f"Cho {data.get('seconds', '?')} giay truoc vong chay tiep theo."

    details = " ".join(f"{key}={value}" for key, value in data.items())
    return f"{event} {details}".strip()
