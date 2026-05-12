from enum import Enum


class RegistrationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    FULL = "full"
    NOT_OPEN = "not_open"
    ALREADY_REGISTERED = "already_registered"
    NEED_RELOGIN = "need_relogin"
    RATE_LIMITED = "rate_limited"
    HTTP_ERROR = "http_error"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"

