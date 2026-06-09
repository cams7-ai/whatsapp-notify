from __future__ import annotations

import logging

from config import AppConfig
from domain import AuthenticationError, DomainError, Notification, SendError, TargetNotFoundError

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:
    """Servico para envio completo de notificacoes via WhatsApp Web."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def send(self, target_name: str, message: str) -> None:
        """Valida e envia uma notificacao pelo fluxo que abre e fecha o navegador."""
        try:
            notification = Notification(target_name=target_name, message=message)
        except ValueError as exc:
            raise DomainError(f"Notificacao invalida: {exc}") from exc

        logger.info(
            "Enviando notificacao para %s com %s caracteres",
            notification.target_name,
            len(notification.message),
        )

        config = AppConfig(
            target_name=notification.target_name,
            message=notification.message,
            headless=self.config.headless,
            profile_dir=self.config.profile_dir,
            timeout_seconds=self.config.timeout_seconds,
        )

        try:
            self._run_whatsapp_service(config)
        except (AuthenticationError, TargetNotFoundError, SendError):
            raise
        except Exception as exc:
            logger.exception("Erro inesperado ao enviar notificacao")
            raise DomainError(f"Erro ao enviar notificacao: {exc}") from exc

        logger.info("Notificacao enviada com sucesso para %s", target_name)

    @staticmethod
    def _run_whatsapp_service(config: AppConfig) -> None:
        from whatsapp_service import (
            AuthenticationTimeoutError,
            MessageSendError,
            TargetNotFoundError as PlaywrightTargetNotFoundError,
            WhatsAppNotifyError,
            WhatsAppService,
        )

        try:
            service = WhatsAppService(config=config)
            service.run()
        except AuthenticationTimeoutError as exc:
            raise AuthenticationError(str(exc)) from exc
        except PlaywrightTargetNotFoundError as exc:
            raise TargetNotFoundError(str(exc)) from exc
        except MessageSendError as exc:
            raise SendError(str(exc)) from exc
        except WhatsAppNotifyError as exc:
            raise SendError(f"Erro na automacao: {exc}") from exc
