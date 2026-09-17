import os
import unittest
from unittest.mock import patch

import app.main as main_module
from app.config import build_settings
from app.main import _build_registrar


class MainTests(unittest.TestCase):
    def test_registrar_uses_hidden_terminal_prompt_for_access_code(self):
        with patch.dict(
            os.environ,
            {"PORTAL_USERNAME": "student", "PORTAL_PASSWORD": "secret"},
            clear=False,
        ):
            settings = build_settings(
                {
                    "portal": {
                        "login_url": "https://example.test/login",
                        "registration_url": "https://example.test/register",
                    },
                    "courses": [{"id": "6509", "name": "DevOps"}],
                    "database": {"url": "sqlite:///:memory:"},
                }
            )

        self.assertTrue(
            hasattr(main_module, "getpass"),
            "main must use getpass for the access code",
        )
        with patch("app.main.getpass", return_value="654321") as prompt:
            registrar = _build_registrar(settings)
            provider = registrar.portal._access_code_provider
            self.assertIsNotNone(provider)
            self.assertEqual(provider(), "654321")

        prompt.assert_called_once_with("Nhap ma xac thuc email: ")


if __name__ == "__main__":
    unittest.main()
