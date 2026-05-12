import tempfile
import unittest
from pathlib import Path

from app.config import build_settings
from app.services.state_store import StateStore


def _settings(db_path: Path, courses):
    return build_settings(
        {
            "portal": {
                "login_url": "https://example.test/login",
                "registration_url": "https://example.test/register",
            },
            "courses": courses,
            "database": {"url": f"sqlite:///{db_path}"},
        },
        require_secrets=False,
    )


class StateStoreTests(unittest.TestCase):
    def test_courses_removed_from_config_are_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.db"

            first_settings = _settings(
                db_path,
                [
                    {"id": "6102", "name": "Old course", "priority": 1},
                    {"id": "6317", "name": "Linux", "priority": 2},
                ],
            )
            store = StateStore(first_settings)
            store.init_db()
            store.upsert_courses(first_settings.courses)

            second_settings = _settings(
                db_path,
                [{"id": "6317", "name": "Linux", "priority": 1}],
            )
            store = StateStore(second_settings)
            store.upsert_courses(second_settings.courses)

            pending_ids = {course.id for course in store.list_pending_courses()}
            self.assertEqual(pending_ids, {"6317"})


if __name__ == "__main__":
    unittest.main()

