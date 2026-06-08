from config import AppConfig
from repositories.i_notification_repository import INotificationRepository

class PlaywrightNotificationRepository(INotificationRepository):
    """Implementação do repositório usando Playwright e WhatsApp Web."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def send(self, target_name: str, message: str) -> None:
        """Envia mensagem via WhatsApp Web com Playwright."""
        from whatsapp_service import WhatsAppService
        from whatsapp_service import (
            AuthenticationTimeoutError,
            MessageSendError,
            TargetNotFoundError as PlaywrightTargetNotFoundError,
            WhatsAppNotifyError,
        )
        from domain import (
            AuthenticationError,
            SendError,
            TargetNotFoundError,
        )

        modified_config = AppConfig(
            target_name=target_name,
            message=message,
            headless=self.config.headless,
            profile_dir=self.config.profile_dir,
            timeout_seconds=self.config.timeout_seconds,
        )

        try:
            service = WhatsAppService(config=modified_config)
            service.run()
        except AuthenticationTimeoutError as exc:
            raise AuthenticationError(str(exc)) from exc
        except PlaywrightTargetNotFoundError as exc:
            raise TargetNotFoundError(str(exc)) from exc
        except MessageSendError as exc:
            raise SendError(str(exc)) from exc
        except WhatsAppNotifyError as exc:
            raise SendError(f"Erro na automação: {exc}") from exc
