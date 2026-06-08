"""Domain layer com modelos e excecoes de negocio."""

from domain.exceptions.error import (
    AuthenticationError,
    DomainError,
    SendError,
    SessionAlreadyOpenError,
    SessionClosedError,
    SessionStartError,
    SessionStopError,
    TargetNotFoundError,
)
from domain.models.notification import Notification

__all__ = [
    "DomainError",
    "AuthenticationError",
    "TargetNotFoundError",
    "SendError",
    "SessionAlreadyOpenError",
    "SessionClosedError",
    "SessionStartError",
    "SessionStopError",
    "Notification",
]
