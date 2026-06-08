from __future__ import annotations
from abc import ABC, abstractmethod

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