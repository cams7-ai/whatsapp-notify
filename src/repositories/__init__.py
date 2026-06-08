"""Camada de repositório com interfaces e implementações.

Repository Pattern desacopla a lógica de negócio da implementação
de persistência/integração (Playwright, banco de dados, etc).
"""

from repositories.i_notification_repository import INotificationRepository
from repositories.playwright_notification_repository import PlaywrightNotificationRepository

__all__ = ["INotificationRepository", "PlaywrightNotificationRepository"]
