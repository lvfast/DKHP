from __future__ import annotations

import asyncio
import json
import logging
from urllib import parse, request

from app.config import NotificationSettings
from app.logging_config import event_extra

logger = logging.getLogger(__name__)


class Notifier:
    async def send(self, message: str) -> None:
        raise NotImplementedError


class LogNotifier(Notifier):
    async def send(self, message: str) -> None:
        logger.info("notification", extra=event_extra(message=message))


class TelegramNotifier(Notifier):
    def __init__(self, settings: NotificationSettings) -> None:
        self.settings = settings

    async def send(self, message: str) -> None:
        if (
            not self.settings.telegram_enabled
            or not self.settings.telegram_bot_token
            or not self.settings.telegram_chat_id
        ):
            logger.info("telegram_disabled", extra=event_extra(message=message))
            return
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: str) -> None:
        url = (
            "https://api.telegram.org/bot"
            f"{self.settings.telegram_bot_token}/sendMessage"
        )
        payload = parse.urlencode(
            {
                "chat_id": self.settings.telegram_chat_id,
                "text": message,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("ok"):
                    logger.warning("telegram_send_failed", extra=event_extra(response=data))
        except Exception as exc:
            logger.warning("telegram_send_failed", extra=event_extra(error=str(exc)))


def build_notifier(settings: NotificationSettings) -> Notifier:
    if settings.telegram_enabled:
        return TelegramNotifier(settings)
    return LogNotifier()

