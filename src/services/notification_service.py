
import logging

from domain import Notification, DomainError
from repositories import INotificationRepository
from services.i_notification_service import INotificationService

class NotificationService(INotificationService):
    """Serviço para envio de notificações.

    Orquestra a lógica de envio de mensagens, validação e delegação
    para o repositório responsável pela integração com WhatsApp.
    """

    def __init__(
        self,
        repository: INotificationRepository,
        logger: logging.Logger,
    ) -> None:
        self.repository = repository
        self.logger = logger

    def send(self, target_name: str, message: str) -> None:
        """Envia uma notificação validada e rastreada.

        Args:
            target_name: nome do contato ou grupo
            message: texto da mensagem

        Raises:
            Exceções de domínio (AuthenticationError, TargetNotFoundError, SendError)
        """
        # Validação de domínio
        try:
            notification = Notification(target_name=target_name, message=message)
        except ValueError as e:
            raise DomainError(f"Notificação inválida: {e}") from e

        self.logger.info(
            "Enviando notificação para %s: %s",
            notification.target_name,
            notification.message[:50],  # log dos primeiros 50 chars
        )

        # Delegação ao repositório (adaptador concreto)
        try:
            self.repository.send(notification.target_name, notification.message)
        except DomainError:
            # Re-emite exceções de domínio (já mapeadas pelo repositório)
            raise
        except Exception as e:
            # Converte exceções inesperadas em erro de domínio
            self.logger.exception("Erro inesperado ao enviar notificação")
            raise DomainError(f"Erro ao enviar notificação: {e}") from e

        self.logger.info("Notificação enviada com sucesso para %s", target_name)

