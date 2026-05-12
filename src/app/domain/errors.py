class AppError(Exception):
    """Base application error."""


class ConfigError(AppError):
    """Raised when configuration is missing or invalid."""


class PortalError(AppError):
    """Raised when portal communication fails unexpectedly."""


class ParseError(AppError):
    """Raised when a portal response cannot be parsed safely."""

