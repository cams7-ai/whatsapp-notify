from __future__ import annotations
from abc import ABC, abstractmethod

class INotificationService(ABC):
    """‘Interface’ para serviço de notificações.

    Define o contrato para envio de notificações, independente do canal.
    """

    @abstractmethod
    def send(self, target_name: str, message: str) -> None:
        """Envia uma notificação para um contato/grupo.

        Args:
            target_name: nome do contato ou grupo
            message: texto da mensagem
        """
        ...  # pragma: no cover