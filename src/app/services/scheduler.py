from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.logging_config import event_extra
from app.services.registrar import Registrar

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, settings: Settings, registrar: Registrar) -> None:
        self.settings = settings
        self.registrar = registrar
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def run_forever(self) -> None:
        logger.info("service_started")
        while not self._stopped.is_set():
            all_success = await self.registrar.run_once()
            if all_success and self.settings.runtime.stop_when_all_success:
                logger.info("all_courses_success")
                break
            interval = (
                self.settings.runtime.hot_interval_seconds
                if self.settings.runtime.mode == "hot"
                else self.settings.runtime.normal_interval_seconds
            )
            logger.info("scheduler_sleep", extra=event_extra(seconds=interval))
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=interval)
            except TimeoutError:
                continue
        logger.info("service_stopped")

