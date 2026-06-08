"""Camada de serviço com lógica de negócio.

Service Layer orquestra a lógica de domínio e delega para repositórios.
Isto mantém a lógica de negócio independente de frameworks e detalhes de
implementação (Playwright, HTTP, etc).
"""
from services.i_notification_service import INotificationService
from services.notification_service import NotificationService

__all__ = ['INotificationService', 'NotificationService']



