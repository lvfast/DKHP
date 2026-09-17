from __future__ import annotations

import logging

from app.config import Settings
from app.domain.models import RegistrationResult
from app.domain.statuses import RegistrationStatus
from app.logging_config import event_extra
from app.portal.client import PortalClient
from app.services.notifier import Notifier
from app.services.rate_limiter import RateLimiter
from app.services.state_store import StateStore

logger = logging.getLogger(__name__)


class Registrar:
    def __init__(
        self,
        settings: Settings,
        portal: PortalClient,
        store: StateStore,
        notifier: Notifier,
        rate_limiter: RateLimiter,
    ) -> None:
        self.settings = settings
        self.portal = portal
        self.store = store
        self.notifier = notifier
        self.rate_limiter = rate_limiter

    async def run_once(self, *, dry_run: bool | None = None) -> bool:
        effective_dry_run = self.settings.runtime.dry_run if dry_run is None else dry_run
        self.store.init_db()
        self.store.upsert_courses(self.settings.courses)

        await self.portal.ensure_logged_in()
        if not await self.portal.check_registration_page():
            self.store.save_event(
                "warning",
                "registration_page_check_failed",
                "Registration page check failed",
                {},
            )
            return False

        for course in self.store.list_pending_courses():
            await self.rate_limiter.acquire()

            if effective_dry_run:
                result = RegistrationResult(
                    status=RegistrationStatus.UNKNOWN,
                    message="dry run: would register course",
                )
                attempt_count = self.store.save_attempt(course.id, result)
                logger.info(
                    "dry_run_register_course",
                    extra=event_extra(
                        course_id=course.id,
                        course_name=course.name,
                        attempt_count=attempt_count,
                    ),
                )
                continue

            result = await self.portal.register_course(course.id)
            attempt_count = self.store.save_attempt(course.id, result)
            logger.info(
                "course_registration_attempt",
                extra=event_extra(
                    course_id=course.id,
                    course_name=course.name,
                    status=result.status.value,
                    http_status=result.http_status,
                    duration_ms=result.duration_ms,
                    attempt_count=attempt_count,
                    message=result.message,
                    response_excerpt=result.response_excerpt,
                ),
            )
            if result.status == RegistrationStatus.NEED_RELOGIN:
                self.portal.invalidate_session()
            await self._notify_if_needed(course.name, course.id, result, attempt_count)

        return self.store.all_success()

    async def _notify_if_needed(
        self,
        course_name: str,
        course_id: str,
        result: RegistrationResult,
        attempt_count: int,
    ) -> None:
        if result.status == RegistrationStatus.SUCCESS:
            await self.notifier.send(
                "\n".join(
                    [
                        "Course registration succeeded",
                        f"Course: {course_name}",
                        f"Class id: {course_id}",
                        f"Attempts: {attempt_count}",
                    ]
                )
            )
            return

        if result.status == RegistrationStatus.NEED_RELOGIN:
            await self.notifier.send(f"Portal session expired: {result.message}")
            return

        if (
            result.status in {RegistrationStatus.FAILED, RegistrationStatus.HTTP_ERROR}
            and attempt_count >= self.settings.runtime.max_failures_before_notify
        ):
            await self.notifier.send(
                "\n".join(
                    [
                        "Course registration failed repeatedly",
                        f"Course: {course_name}",
                        f"Class id: {course_id}",
                        f"Last error: {result.message}",
                    ]
                )
            )
