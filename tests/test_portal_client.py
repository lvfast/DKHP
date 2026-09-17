import asyncio
import inspect
import os
import unittest
from unittest.mock import patch

from app.config import build_settings
from app.domain.models import LoginResult
from app.domain.statuses import RegistrationStatus
from app.portal.client import PortalClient


LOGIN_HTML = """
<html><form>
  <input type="hidden" name="__VIEWSTATE" value="login-state">
</form></html>
"""

ACCESS_CODE_HTML = """
<html><form method="post" action="/Verify-Access-Code?returnUrl=%2Fregister">
  <input type="hidden" name="__VIEWSTATE" value="otp-state">
  <input type="hidden" name="__EVENTVALIDATION" value="otp-event">
  <input type="text" name="dnn$ctr670$ViewTwoFactor$txtOtp" value="">
  <input type="submit" name="dnn$ctr670$ViewTwoFactor$btnVerify" value="Verify">
</form></html>
"""

REGISTRATION_HTML = "<html><body>Sinh vien CLC</body></html>"


def _settings():
    with patch.dict(
        os.environ,
        {"PORTAL_USERNAME": "student", "PORTAL_PASSWORD": "secret"},
        clear=False,
    ):
        return build_settings(
            {
                "portal": {
                    "login_url": "https://example.test/Login",
                    "registration_url": "https://example.test/register",
                    "expected_registration_page_text": "Sinh vien CLC",
                },
                "courses": [{"id": "6509", "name": "DevOps"}],
            }
        )


class FakePortalClient(PortalClient):
    def __init__(self, *args, responses, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = list(responses)
        self.requests = []

    def _request(self, method, url, *, data=None, headers=None, multipart=False):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "data": data,
                "headers": headers,
                "multipart": multipart,
            }
        )
        return self.responses.pop(0)

    def _has_auth_cookie(self):
        return True


class LoginCountingPortalClient(PortalClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.login_calls = 0

    async def login(self):
        self.login_calls += 1
        return LoginResult(success=True, message="login ok", http_status=200)


class PortalClientTests(unittest.TestCase):
    def test_registration_page_check_rejects_access_code_redirect(self):
        client = FakePortalClient(
            _settings(),
            responses=[
                (
                    200,
                    REGISTRATION_HTML,
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                )
            ],
        )

        self.assertFalse(client._check_registration_page_sync())

    def test_registration_redirect_to_access_code_requires_relogin(self):
        client = FakePortalClient(
            _settings(),
            responses=[
                (
                    200,
                    "{}",
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                )
            ],
        )

        result = client._register_course_sync("6509")

        self.assertEqual(result.status, RegistrationStatus.NEED_RELOGIN)

    def test_invalidate_session_requires_login_again(self):
        client = PortalClient(_settings())
        client._logged_in_at = 123.0
        invalidate_session = getattr(client, "invalidate_session", None)
        self.assertIsNotNone(
            invalidate_session,
            "PortalClient must expose session invalidation",
        )

        invalidate_session()

        self.assertEqual(client._logged_in_at, 0.0)

    def test_active_session_does_not_trigger_periodic_login(self):
        client = LoginCountingPortalClient(_settings())
        client._logged_in_at = 1.0

        asyncio.run(client.ensure_logged_in())

        self.assertEqual(client.login_calls, 0)

    def test_login_submits_access_code_before_reporting_success(self):
        self.assertIn(
            "access_code_provider",
            inspect.signature(PortalClient.__init__).parameters,
            "PortalClient must accept an access-code provider",
        )
        client = FakePortalClient(
            _settings(),
            access_code_provider=lambda: "123456",
            responses=[
                (200, LOGIN_HTML, "https://example.test/Login"),
                (
                    200,
                    ACCESS_CODE_HTML,
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                ),
                (200, REGISTRATION_HTML, "https://example.test/register"),
            ],
        )

        result = client._login_sync()

        self.assertTrue(result.success)
        self.assertEqual(len(client.requests), 3)
        verification_request = client.requests[2]
        self.assertEqual(
            verification_request["url"],
            "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
        )
        self.assertEqual(
            verification_request["data"]["dnn$ctr670$ViewTwoFactor$txtOtp"],
            "123456",
        )
        self.assertEqual(verification_request["data"]["__VIEWSTATE"], "otp-state")
        self.assertNotIn("123456", result.message)

    def test_login_rejects_invalid_access_code(self):
        self.assertIn(
            "access_code_provider",
            inspect.signature(PortalClient.__init__).parameters,
            "PortalClient must accept an access-code provider",
        )
        client = FakePortalClient(
            _settings(),
            access_code_provider=lambda: "wrong-code",
            responses=[
                (200, LOGIN_HTML, "https://example.test/Login"),
                (
                    200,
                    ACCESS_CODE_HTML,
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                ),
                (
                    200,
                    ACCESS_CODE_HTML,
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                ),
            ],
        )

        result = client._login_sync()

        self.assertFalse(result.success)
        self.assertIn("verification", result.message.lower())
        self.assertNotIn("wrong-code", result.message)

    def test_login_rejects_verification_redirect_even_when_page_text_matches(self):
        client = FakePortalClient(
            _settings(),
            access_code_provider=lambda: "123456",
            responses=[
                (200, LOGIN_HTML, "https://example.test/Login"),
                (
                    200,
                    ACCESS_CODE_HTML,
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                ),
                (
                    200,
                    REGISTRATION_HTML,
                    "https://example.test/Verify-Access-Code?returnUrl=%2Fregister",
                ),
            ],
        )

        result = client._login_sync()

        self.assertFalse(result.success)
        self.assertIn("verification", result.message.lower())


if __name__ == "__main__":
    unittest.main()
