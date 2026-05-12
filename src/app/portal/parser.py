from __future__ import annotations

from html.parser import HTMLParser
import json
import re
import unicodedata
from typing import Any

from app.domain.errors import ParseError
from app.domain.models import RegistrationResult
from app.domain.statuses import RegistrationStatus


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inputs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        name = attr_map.get("name")
        if name:
            self.inputs[name] = attr_map.get("value", "")


def parse_login_form(html: str) -> dict[str, str]:
    parser = _InputParser()
    parser.feed(html)
    if not parser.inputs:
        raise ParseError("Login form does not contain named inputs")
    return parser.inputs


def parse_registration_response(status_code: int, body: str) -> RegistrationResult:
    excerpt = _excerpt(body)
    if status_code in {401, 403}:
        return RegistrationResult(
            status=RegistrationStatus.NEED_RELOGIN,
            message="Portal returned an authentication error",
            http_status=status_code,
            response_excerpt=excerpt,
        )
    if status_code == 429:
        return RegistrationResult(
            status=RegistrationStatus.RATE_LIMITED,
            message="Portal rate limited the request",
            http_status=status_code,
            response_excerpt=excerpt,
        )
    if status_code >= 500:
        return RegistrationResult(
            status=RegistrationStatus.HTTP_ERROR,
            message="Portal returned a server error",
            http_status=status_code,
            response_excerpt=excerpt,
        )
    if _looks_like_login_page(body):
        return RegistrationResult(
            status=RegistrationStatus.NEED_RELOGIN,
            message="Portal returned a login page",
            http_status=status_code,
            response_excerpt=excerpt,
        )

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return RegistrationResult(
            status=RegistrationStatus.PARSE_ERROR,
            message="Registration response is not valid JSON",
            http_status=status_code,
            response_excerpt=excerpt,
        )

    status = _status_from_json(parsed)
    message = _message_from_json(parsed)
    return RegistrationResult(
        status=status,
        message=message or status.value,
        http_status=status_code,
        response_excerpt=excerpt,
    )


def _status_from_json(parsed: Any) -> RegistrationStatus:
    if isinstance(parsed, dict):
        explicit_status = _first_present(parsed, "status", "code", "result", "results")
        success = _first_present(parsed, "success", "is_success", "ok")
        text = " ".join(
            str(value)
            for value in [
                explicit_status,
                _first_present(parsed, "result", "results"),
                _first_present(parsed, "message", "msg", "error", "notification"),
            ]
            if value is not None
        )
        normalized = _normalize(text)

        if success is True:
            return RegistrationStatus.SUCCESS
        if success is False and not normalized:
            return RegistrationStatus.FAILED
        return _classify_text(normalized)

    if isinstance(parsed, list):
        normalized = _normalize(json.dumps(parsed, ensure_ascii=False))
        return _classify_text(normalized)

    return RegistrationStatus.UNKNOWN


def _classify_text(text: str) -> RegistrationStatus:
    if any(term in text for term in ("khong thanh cong", "fail", "failed", "loi")):
        return RegistrationStatus.FAILED
    if any(term in text for term in ("success", "thanh cong", "dang ky thanh cong")):
        return RegistrationStatus.SUCCESS
    if any(term in text for term in ("already", "da dang ky", "trung lich")):
        return RegistrationStatus.ALREADY_REGISTERED
    if any(term in text for term in ("full", "het slot", "het cho", "het so luong")):
        return RegistrationStatus.FULL
    if any(term in text for term in ("not open", "chua mo", "khong trong thoi gian")):
        return RegistrationStatus.NOT_OPEN
    if any(term in text for term in ("login", "dang nhap", "session")):
        return RegistrationStatus.NEED_RELOGIN
    if any(term in text for term in ("rate", "too many", "429")):
        return RegistrationStatus.RATE_LIMITED
    return RegistrationStatus.UNKNOWN


def _message_from_json(parsed: Any) -> str:
    if not isinstance(parsed, dict):
        return ""
    value = _first_present(parsed, "message", "msg", "error", "notification", "description")
    if value is None:
        return ""
    return str(value)


def _first_present(data: dict[str, Any], *keys: str) -> Any:
    lowered = {key.lower(): value for key, value in data.items()}
    for key in keys:
        if key in data:
            return data[key]
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _looks_like_login_page(body: str) -> bool:
    normalized = _normalize(body)
    return bool(
        "<html" in normalized
        and (
            "password" in normalized
            or "dang nhap" in normalized
            or "login" in normalized
        )
    )


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"\s+", " ", ascii_text)
    return ascii_text


def _excerpt(body: str, limit: int = 500) -> str:
    compact = re.sub(r"\s+", " ", body).strip()
    return compact[:limit]
