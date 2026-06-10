"""Domain layer com modelos e excecoes de negocio."""

from domain.exceptions.error import (
    AuthenticationError,
    DomainError,
    QRCodeNotFoundError,
    SendError,
    SessionAlreadyOpenError,
    SessionClosedError,
    SessionStartError,
    SessionStopError,
    TargetNotFoundError,
)
from domain.models.notification import Notification
from domain.models.session_status import SessionStatus

__all__ = [
    "DomainError",
    "AuthenticationError",
    "QRCodeNotFoundError",
    "TargetNotFoundError",
    "SendError",
    "SessionAlreadyOpenError",
    "SessionClosedError",
    "SessionStartError",
    "SessionStopError",
    "Notification",
    "SessionStatus",
]
