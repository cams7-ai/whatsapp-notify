import pytest

from config import AppConfig
from domain import (
    AuthenticationError,
    DomainError,
    Notification,
    SendError,
    TargetNotFoundError,
)
from services import WhatsAppNotificationService
import whatsapp_service as ws_mod


class DummyWhatsAppService:
    run_error = None
    instances = []

    def __init__(self, config):
        self.config = config
        self.ran = False
        self.instances.append(self)

    def run(self):
        self.ran = True
        if self.run_error:
            raise self.run_error


@pytest.fixture(autouse=True)
def reset_dummy_service(monkeypatch):
    DummyWhatsAppService.run_error = None
    DummyWhatsAppService.instances = []
    monkeypatch.setattr(ws_mod, "WhatsAppService", DummyWhatsAppService)


@pytest.fixture
def config(tmp_path):
    return AppConfig(
        target_name="Grupo Env",
        message="Mensagem Env",
        headless=True,
        profile_dir=tmp_path,
        timeout_seconds=1,
    )


@pytest.fixture
def service(config):
    return WhatsAppNotificationService(config=config)


class TestWhatsAppNotificationService:
    def test_send_runs_whatsapp_service_with_valid_notification(self, service, config):
        service.send(target_name="Grupo Teste", message="Ola")

        instance = DummyWhatsAppService.instances[0]
        assert instance.ran is True
        assert instance.config.target_name == "Grupo Teste"
        assert instance.config.message == "Ola"
        assert instance.config.headless is config.headless
        assert instance.config.profile_dir == config.profile_dir
        assert instance.config.timeout_seconds == config.timeout_seconds

    def test_send_maps_authentication_timeout(self, service):
        DummyWhatsAppService.run_error = ws_mod.AuthenticationTimeoutError("timeout")

        with pytest.raises(AuthenticationError, match="timeout"):
            service.send("Grupo", "Msg")

    def test_send_maps_target_not_found(self, service):
        DummyWhatsAppService.run_error = ws_mod.TargetNotFoundError("not found")

        with pytest.raises(TargetNotFoundError, match="not found"):
            service.send("Desconhecido", "Msg")

    def test_send_maps_message_error(self, service):
        DummyWhatsAppService.run_error = ws_mod.MessageSendError("failed")

        with pytest.raises(SendError, match="failed"):
            service.send("Grupo", "Msg")

    def test_send_maps_whatsapp_notify_error(self, service):
        DummyWhatsAppService.run_error = ws_mod.WhatsAppNotifyError("automation")

        with pytest.raises(SendError, match="Erro na automacao: automation"):
            service.send("Grupo", "Msg")

    def test_send_raises_domain_error_on_invalid_notification(self, service):
        with pytest.raises(DomainError, match="nao pode estar vazio|não pode estar vazio"):
            service.send(target_name="", message="Valid message")

    def test_send_raises_domain_error_on_empty_message(self, service):
        with pytest.raises(DomainError, match="nao pode estar vazio|não pode estar vazio"):
            service.send(target_name="Valid", message="")

    def test_send_wraps_unexpected_exception(self, service):
        DummyWhatsAppService.run_error = RuntimeError("Unexpected!")

        with pytest.raises(DomainError, match="Erro ao enviar notificacao"):
            service.send("Grupo", "Msg")


class TestNotification:
    def test_notification_creation_with_valid_data(self):
        notif = Notification(target_name="Grupo", message="Ola")
        assert notif.target_name == "Grupo"
        assert notif.message == "Ola"

    def test_notification_raises_on_empty_target(self):
        with pytest.raises(ValueError, match="nao pode estar vazio|não pode estar vazio"):
            Notification(target_name="", message="Valid")

    def test_notification_raises_on_whitespace_target(self):
        with pytest.raises(ValueError, match="nao pode estar vazio|não pode estar vazio"):
            Notification(target_name="   ", message="Valid")

    def test_notification_raises_on_empty_message(self):
        with pytest.raises(ValueError, match="nao pode estar vazio|não pode estar vazio"):
            Notification(target_name="Valid", message="")

    def test_notification_is_immutable(self):
        notif = Notification(target_name="Grupo", message="Ola")

        with pytest.raises(AttributeError):
            notif.target_name = "Outro"
