from __future__ import annotations

import asyncio
from http.cookiejar import CookieJar
import logging
import secrets
from time import monotonic
from typing import Any
from urllib import parse, request

from app.config import Settings
from app.domain.models import LoginResult, RegistrationResult
from app.domain.statuses import RegistrationStatus
from app.logging_config import event_extra
from app.portal.parser import parse_login_form, parse_registration_response

logger = logging.getLogger(__name__)


class PortalClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cookies = CookieJar()
        self._opener = request.build_opener(request.HTTPCookieProcessor(self._cookies))
        self._logged_in_at = 0.0

    async def login(self) -> LoginResult:
        return await asyncio.to_thread(self._login_sync)

    async def ensure_logged_in(self) -> None:
        if monotonic() - self._logged_in_at < self.settings.runtime.relogin_after_seconds:
            return
        result = await self.login()
        if not result.success:
            raise RuntimeError(f"Portal login failed: {result.message}")

    async def check_registration_page(self) -> bool:
        return await asyncio.to_thread(self._check_registration_page_sync)

    async def register_course(self, course_id: str) -> RegistrationResult:
        return await asyncio.to_thread(self._register_course_sync, course_id)

    async def close(self) -> None:
        return None

    def _login_sync(self) -> LoginResult:
        try:
            get_status, html = self._request("GET", self.settings.portal.login_url)
            hidden = parse_login_form(html)
            payload = {
                **hidden,
                self.settings.portal.login_username_field: self.settings.student.username,
                self.settings.portal.login_password_field: self.settings.student.password,
            }
            if self.settings.portal.login_event_target:
                payload["__EVENTTARGET"] = self.settings.portal.login_event_target
            post_status, post_body = self._request(
                "POST",
                self.settings.portal.login_url,
                data=payload,
                headers={
                    "Referer": self.settings.portal.login_url,
                    "Origin": _origin_from_url(self.settings.portal.login_url),
                },
                multipart=self.settings.portal.login_multipart,
            )
        except Exception as exc:
            logger.warning("portal_login_failed", extra=event_extra(error=str(exc)))
            return LoginResult(success=False, message=str(exc))

        if post_status >= 400:
            return LoginResult(
                success=False,
                message=f"Login returned HTTP {post_status}",
                http_status=post_status,
            )
        if self._has_auth_cookie():
            self._logged_in_at = monotonic()
            logger.info("portal_login_success", extra=event_extra(http_status=post_status))
            return LoginResult(success=True, message="login ok", http_status=post_status)
        if "password" in post_body.lower() and "login" in post_body.lower():
            return LoginResult(
                success=False,
                message="Portal still appears to be on login page",
                http_status=post_status,
            )

        self._logged_in_at = monotonic()
        logger.info("portal_login_success", extra=event_extra(http_status=post_status))
        return LoginResult(success=True, message="login ok", http_status=get_status)

    def _check_registration_page_sync(self) -> bool:
        status, body = self._request("GET", self.settings.portal.registration_url)
        if status >= 400:
            logger.warning(
                "registration_page_unavailable",
                extra=event_extra(http_status=status),
            )
            return False
        expected = self.settings.portal.expected_registration_page_text
        if expected and expected not in body:
            logger.warning("registration_page_text_missing")
            return False
        return True

    def _register_course_sync(self, course_id: str) -> RegistrationResult:
        payload = {
            "action": self.settings.portal.registration_action,
            self.settings.portal.registration_course_field: course_id,
        }
        started = monotonic()
        try:
            status, body = self._request(
                "POST",
                self.settings.portal.registration_url,
                data=payload,
                headers={
                    "Accept": "*/*",
                    "Referer": self.settings.portal.registration_url,
                    "Origin": _origin_from_url(self.settings.portal.registration_url),
                    "X-OFFICIAL-REQUEST": "TRUE",
                    "X-Requested-With": "XMLHttpRequest",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                },
                multipart=self.settings.portal.registration_multipart,
            )
        except Exception as exc:
            return RegistrationResult(
                status=RegistrationStatus.HTTP_ERROR,
                message=str(exc),
                duration_ms=int((monotonic() - started) * 1000),
            )
        result = parse_registration_response(status, body)
        return RegistrationResult(
            status=result.status,
            message=result.message,
            http_status=result.http_status,
            response_excerpt=result.response_excerpt,
            duration_ms=int((monotonic() - started) * 1000),
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        multipart: bool = False,
    ) -> tuple[int, str]:
        request_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        if headers:
            request_headers.update(headers)
        body: bytes | None = None
        if data is not None:
            if multipart:
                body, content_type = _encode_multipart_form(data)
                request_headers.setdefault("Content-Type", content_type)
            else:
                body = parse.urlencode(data).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        req = request.Request(url, data=body, headers=request_headers, method=method)
        with self._opener.open(req, timeout=self.settings.runtime.request_timeout_seconds) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            response_body = resp.read().decode(charset, errors="replace")
            return resp.status, response_body

    def _has_auth_cookie(self) -> bool:
        return any(
            cookie.name.lower().startswith(".aspxauth") or "auth" in cookie.name.lower()
            for cookie in self._cookies
        )


def _origin_from_url(url: str) -> str:
    parsed = parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _encode_multipart_form(data: dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"----WebKitFormBoundary{secrets.token_hex(12)}"
    chunks: list[bytes] = []
    for key, value in data.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
