from __future__ import annotations

from datetime import UTC, datetime
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Iterator

from app.config import Settings, sqlite_path_from_url
from app.domain.models import CourseConfig, CourseState, RegistrationResult
from app.domain.statuses import RegistrationStatus


class StateStore:
    def __init__(self, settings: Settings) -> None:
        self.path = sqlite_path_from_url(settings.database.url)

    def init_db(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_attempt_at TEXT,
                    success_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_message TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    message TEXT NOT NULL,
                    response_excerpt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    duration_ms INTEGER,
                    FOREIGN KEY(course_id) REFERENCES courses(id)
                );

                CREATE TABLE IF NOT EXISTS runtime_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )

    def reset_db(self) -> None:
        for suffix in ("", "-shm", "-wal"):
            path = Path(f"{self.path}{suffix}")
            if path.exists():
                path.unlink()
        self.init_db()

    def upsert_courses(self, courses: Iterable[CourseConfig]) -> None:
        course_list = list(courses)
        configured_ids = {course.id for course in course_list}
        now = _now()
        with self._connect() as conn:
            if configured_ids:
                placeholders = ", ".join("?" for _ in configured_ids)
                conn.execute(
                    f"""
                    UPDATE courses
                    SET enabled = 0,
                        updated_at = ?,
                        last_message = 'disabled because course is no longer in config'
                    WHERE id NOT IN ({placeholders})
                    """,
                    (now, *configured_ids),
                )

            for course in course_list:
                conn.execute(
                    """
                    INSERT INTO courses (
                        id, name, priority, enabled, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        priority=excluded.priority,
                        enabled=excluded.enabled,
                        updated_at=excluded.updated_at
                    """,
                    (
                        course.id,
                        course.name,
                        course.priority,
                        int(course.enabled),
                        RegistrationStatus.UNKNOWN.value,
                        now,
                        now,
                    ),
                )

    def list_pending_courses(self) -> list[CourseState]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM courses
                WHERE enabled = 1 AND status != ?
                ORDER BY priority ASC, id ASC
                """,
                (RegistrationStatus.SUCCESS.value,),
            ).fetchall()
        return [_row_to_course_state(row) for row in rows]

    def save_attempt(self, course_id: str, result: RegistrationResult) -> int:
        now = _now()
        success_at = now if result.status == RegistrationStatus.SUCCESS else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO attempts (
                    course_id, status, http_status, message, response_excerpt,
                    created_at, duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    result.status.value,
                    result.http_status,
                    result.message,
                    result.response_excerpt,
                    now,
                    result.duration_ms,
                ),
            )
            conn.execute(
                """
                UPDATE courses
                SET status = ?,
                    updated_at = ?,
                    last_attempt_at = ?,
                    success_at = COALESCE(success_at, ?),
                    attempt_count = attempt_count + 1,
                    last_message = ?
                WHERE id = ?
                """,
                (
                    result.status.value,
                    now,
                    now,
                    success_at,
                    result.message,
                    course_id,
                ),
            )
            row = conn.execute(
                "SELECT attempt_count FROM courses WHERE id = ?",
                (course_id,),
            ).fetchone()
        return int(row["attempt_count"]) if row else 0

    def save_event(self, level: str, event_type: str, message: str, metadata: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_events (level, event_type, message, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (level, event_type, message, _now(), json.dumps(metadata, ensure_ascii=True)),
            )

    def all_success(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM courses
                WHERE enabled = 1 AND status != ?
                """,
                (RegistrationStatus.SUCCESS.value,),
            ).fetchone()
        return bool(row and row["count"] == 0)

    def healthcheck(self) -> bool:
        self.init_db()
        with self._connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def _row_to_course_state(row: sqlite3.Row) -> CourseState:
    return CourseState(
        id=str(row["id"]),
        name=str(row["name"]),
        priority=int(row["priority"]),
        enabled=bool(row["enabled"]),
        status=RegistrationStatus(str(row["status"])),
        attempt_count=int(row["attempt_count"]),
        last_message=str(row["last_message"]),
        last_attempt_at=_parse_datetime(row["last_attempt_at"]),
        success_at=_parse_datetime(row["success_at"]),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
