"""Camada de repositório com interfaces e implementações.

Repository Pattern desacopla a lógica de negócio da implementação
de persistência/integração (Playwright, banco de dados, etc).
"""

from repositories.interfaces.notification_repository import NotificationRepository
from repositories.playwright_notification_repository import PlaywrightNotificationRepository

__all__ = ["NotificationRepository", "PlaywrightNotificationRepository"]
