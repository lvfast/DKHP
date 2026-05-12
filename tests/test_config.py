import os
import unittest

from app.config import build_settings
from app.domain.errors import ConfigError


class ConfigTests(unittest.TestCase):
    def setUp(self):
        os.environ["PORTAL_USERNAME"] = "student"
        os.environ["PORTAL_PASSWORD"] = "secret"

    def test_valid_config_loads_courses_and_credentials(self):
        settings = build_settings(
            {
                "portal": {
                    "login_url": "https://example.test/login",
                    "registration_url": "https://example.test/register",
                },
                "courses": [{"id": "6101", "name": "Course 1", "priority": 1}],
            }
        )

        self.assertEqual(settings.student.username, "student")
        self.assertEqual(settings.courses[0].id, "6101")

    def test_missing_courses_fails(self):
        with self.assertRaises(ConfigError):
            build_settings(
                {
                    "portal": {
                        "login_url": "https://example.test/login",
                        "registration_url": "https://example.test/register",
                    },
                    "courses": [],
                }
            )


if __name__ == "__main__":
    unittest.main()

