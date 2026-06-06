"""Camada de repositório com interfaces e implementações.

Repository Pattern desacopla a lógica de negócio da implementação
de persistência/integração (Playwright, banco de dados, etc).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging

from app.config import AppConfig


class NotificationRepository(ABC):
    """Interface para enviador de notificações.

    Qualquer implementação de envio deve respeitar este contrato.
    """

    @abstractmethod
    def send(self, target_name: str, message: str) -> None:
        """Envia uma notificação para um contato/grupo.

        Raises:
            AuthenticationError: se não autenticado ou timeout
            TargetNotFoundError: se contato/grupo não existir
            SendError: se falhar ao enviar
        """
        raise NotImplementedError


class PlaywrightNotificationRepository(NotificationRepository):
    """Implementação do repositório usando Playwright + WhatsApp Web.

    Adapta a automação existente (WhatsAppService) para a interface
    de repositório, mantendo compatibilidade.
    """

    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def send(self, target_name: str, message: str) -> None:
        """Envia mensagem via WhatsApp Web + Playwright."""
        # Import aqui para evitar circular dependency
        from app.whatsapp_service import WhatsAppService
        from app.whatsapp_service import (
            AuthenticationTimeoutError,
            MessageSendError,
            TargetNotFoundError as PlaywrightTargetNotFoundError,
            WhatsAppNotifyError,
        )
        from app.domain import (
            AuthenticationError,
            TargetNotFoundError,
            SendError,
        )

        # Cria novo config com os valores específicos desta requisição
        modified_config = AppConfig(
            target_name=target_name,
            message=message,
            headless=self.config.headless,
            profile_dir=self.config.profile_dir,
            timeout_seconds=self.config.timeout_seconds,
        )

        try:
            service = WhatsAppService(config=modified_config, logger=self.logger)
            service.run()
        except AuthenticationTimeoutError as e:
            raise AuthenticationError(str(e)) from e
        except PlaywrightTargetNotFoundError as e:
            raise TargetNotFoundError(str(e)) from e
        except MessageSendError as e:
            raise SendError(str(e)) from e
        except WhatsAppNotifyError as e:
            raise SendError(f"Erro na automação: {e}") from e





