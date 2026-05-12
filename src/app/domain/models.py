from dataclasses import dataclass
from datetime import datetime

from app.domain.statuses import RegistrationStatus


@dataclass(frozen=True)
class CourseConfig:
    id: str
    name: str
    priority: int = 100
    enabled: bool = True


@dataclass(frozen=True)
class LoginResult:
    success: bool
    message: str = ""
    http_status: int | None = None


@dataclass(frozen=True)
class RegistrationResult:
    status: RegistrationStatus
    message: str = ""
    http_status: int | None = None
    response_excerpt: str = ""
    duration_ms: int | None = None


@dataclass(frozen=True)
class CourseState:
    id: str
    name: str
    priority: int
    enabled: bool
    status: RegistrationStatus
    attempt_count: int
    last_message: str = ""
    last_attempt_at: datetime | None = None
    success_at: datetime | None = None

