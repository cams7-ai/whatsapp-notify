"""Teste unitÃ¡rio exemplo da camada de serviço.

Demonstra como a arquitetura Clean + DI facilita testes isolados.
"""

import pytest
from unittest.mock import Mock

from services import INotificationService, NotificationService
from domain import (
    Notification,
    AuthenticationError,
    TargetNotFoundError,
    SendError,
    DomainError,
)

class TestNotificationService:
    """Suite de testes para NotificationService."""

    @pytest.fixture
    def mock_repository(self):
        """Cria um repositório mockado (sem precisar de Playwright)."""
        return Mock()

    @pytest.fixture
    def service(self, mock_repository):
        """Cria instância do serviço com dependÃªncias mockadas."""
        return NotificationService(
            repository=mock_repository
        )

    def test_send_calls_repository_with_valid_notification(self, service: INotificationService, mock_repository):
        """Testa que o serviço delega corretamente ao repositório."""
        service.send(target_name="Grupo Teste", message="Olá")

        mock_repository.send.assert_called_once_with("Grupo Teste", "Olá")

    def test_send_raises_authentication_error_from_repository(self, service: INotificationService, mock_repository):
        """Testa que AuthenticationError do repositório Ã© propagada."""
        mock_repository.send.side_effect = AuthenticationError("Timeout")

        with pytest.raises(AuthenticationError, match="Timeout"):
            service.send("Grupo", "Msg")

    def test_send_raises_target_not_found_error(self, service: INotificationService, mock_repository):
        """Testa que TargetNotFoundError Ã© propagada."""
        mock_repository.send.side_effect = TargetNotFoundError("Not found")

        with pytest.raises(TargetNotFoundError, match="Not found"):
            service.send("Desconhecido", "Msg")

    def test_send_raises_send_error_from_repository(self, service: INotificationService, mock_repository):
        """Testa que SendError do repositório Ã© propagada."""
        mock_repository.send.side_effect = SendError("Failed")

        with pytest.raises(SendError, match="Failed"):
            service.send("Grupo", "Msg")

    def test_send_raises_domain_error_on_invalid_notification(self, service: INotificationService, mock_repository):
        """Testa que notificação inválida (target_name vazio) lança erro de domínio."""
        with pytest.raises(DomainError, match="não pode estar vazio"):
            service.send(target_name="", message="Valid message")

    def test_send_raises_domain_error_on_empty_message(self, service: INotificationService, mock_repository):
        """Testa que mensagem vazia lança erro de domínio."""
        with pytest.raises(DomainError, match="não pode estar vazio"):
            service.send(target_name="Valid", message="")
    
    def test_send_wraps_unexpected_exception(self, service: INotificationService, mock_repository):
        """Testa que exceção inesperada Ã© envelopada em DomainError."""
        mock_repository.send.side_effect = RuntimeError("Unexpected!")

        with pytest.raises(DomainError, match="Erro ao enviar notificação"):
            service.send("Grupo", "Msg")


class TestNotification:
    """Suite de testes para o modelo de domínio Notification."""

    def test_notification_creation_with_valid_data(self):
        """Testa criaÃ§Ã£o válida de notificação."""
        notif = Notification(target_name="Grupo", message="Olá")
        assert notif.target_name == "Grupo"
        assert notif.message == "Olá"

    def test_notification_raises_on_empty_target(self):
        """Testa que target_name vazio lança ValueError."""
        with pytest.raises(ValueError, match="não pode estar vazio"):
            Notification(target_name="", message="Valid")

    def test_notification_raises_on_whitespace_target(self):
        """Testa que target_name só com espaÃ§os lança ValueError."""
        with pytest.raises(ValueError, match="não pode estar vazio"):
            Notification(target_name="   ", message="Valid")

    def test_notification_raises_on_empty_message(self):
        """Testa que message vazia lança ValueError."""
        with pytest.raises(ValueError, match="não pode estar vazio"):
            Notification(target_name="Valid", message="")

    def test_notification_is_immutable(self):
        """Testa que Notification Ã© imutável (frozen dataclass)."""
        notif = Notification(target_name="Grupo", message="Olá")

        with pytest.raises(AttributeError):
            notif.target_name = "Outro"


