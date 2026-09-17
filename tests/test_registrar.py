import asyncio
import unittest

from app.config import build_settings
from app.domain.models import CourseState, RegistrationResult
from app.domain.statuses import RegistrationStatus
from app.services.rate_limiter import RateLimiter
from app.services.registrar import Registrar


class FakePortal:
    def __init__(self):
        self.invalidated = False

    async def ensure_logged_in(self):
        return None

    async def check_registration_page(self):
        return True

    async def register_course(self, course_id):
        return RegistrationResult(
            status=RegistrationStatus.NEED_RELOGIN,
            message="session expired",
            http_status=200,
        )

    def invalidate_session(self):
        self.invalidated = True


class FakeStore:
    def init_db(self):
        return None

    def upsert_courses(self, courses):
        return None

    def list_pending_courses(self):
        return [
            CourseState(
                id="6509",
                name="DevOps",
                priority=1,
                enabled=True,
                status=RegistrationStatus.UNKNOWN,
                attempt_count=0,
            )
        ]

    def save_attempt(self, course_id, result):
        return 1

    def all_success(self):
        return False


class FakeNotifier:
    async def send(self, message):
        return None


class RegistrarTests(unittest.TestCase):
    def test_need_relogin_invalidates_portal_session(self):
        settings = build_settings(
            {
                "portal": {
                    "login_url": "https://example.test/login",
                    "registration_url": "https://example.test/register",
                },
                "courses": [{"id": "6509", "name": "DevOps"}],
            },
            require_secrets=False,
        )
        portal = FakePortal()
        registrar = Registrar(
            settings,
            portal,
            FakeStore(),
            FakeNotifier(),
            RateLimiter(20, jitter_seconds=0),
        )

        asyncio.run(registrar.run_once(dry_run=False))

        self.assertTrue(portal.invalidated)


if __name__ == "__main__":
    unittest.main()
