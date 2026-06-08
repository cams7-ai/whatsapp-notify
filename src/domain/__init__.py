"""Domain layer com modelos e exceções de negócio."""

from domain.exceptions.error import DomainError, NotificationError, AuthenticationError, TargetNotFoundError, SendError
from domain.models.notification import Notification

__all__ = [
    'DomainError',
    'NotificationError',
    'AuthenticationError',
    'TargetNotFoundError',
    'SendError',
    'Notification',]



