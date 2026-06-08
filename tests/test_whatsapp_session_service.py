import pytest

from config import AppConfig
from domain import (
    AuthenticationError,
    SendError,
    SessionAlreadyOpenError,
    SessionClosedError,
    SessionStartError,
    SessionStopError,
    TargetNotFoundError,
)
from services.whatsapp_session_service import WhatsAppSessionService
import services.whatsapp_session_service as session_module
import whatsapp_service as ws_mod

class FakePersistentSession:
    start_error = None
    send_error = None
    stop_error = None

    def __init__(self, config):
        self.config = config
        self.is_open = False
        self.sent = []

    def start(self):
        if self.start_error:
            raise self.start_error
        self.is_open = True

    def send(self, target_name, message):
        if self.send_error:
            raise self.send_error
        self.sent.append((target_name, message))

    def stop(self):
        if self.stop_error:
            raise self.stop_error
        self.is_open = False


@pytest.fixture(autouse=True)
def reset_fake_session(monkeypatch):
    FakePersistentSession.start_error = None
    FakePersistentSession.send_error = None
    FakePersistentSession.stop_error = None
    monkeypatch.setattr(session_module, "PersistentWhatsAppSession", FakePersistentSession)


@pytest.fixture
def config(tmp_path):
    return AppConfig(
        target_name="Grupo",
        message="Ola",
        headless=True,
        profile_dir=tmp_path,
        timeout_seconds=1,
    )


@pytest.fixture
def service():
    return WhatsAppSessionService()


def test_start_opens_persistent_session(service, config):
    service.start(config)

    assert service.is_open


def test_start_rejects_existing_open_session(service, config):
    service.start(config)

    with pytest.raises(SessionAlreadyOpenError):
        service.start(config)


def test_start_maps_authentication_timeout(service, config):
    FakePersistentSession.start_error = ws_mod.AuthenticationTimeoutError("timeout")

    with pytest.raises(AuthenticationError):
        service.start(config)


def test_start_maps_unexpected_error(service, config):
    FakePersistentSession.start_error = RuntimeError("boom")

    with pytest.raises(SessionStartError):
        service.start(config)


def test_send_requires_open_session(service, config):
    with pytest.raises(SessionClosedError):
        service.send(config)


def test_send_uses_open_session(service, config):
    service.start(config)
    service.send(config)

    assert service._session.sent == [("Grupo", "Ola")]


def test_send_maps_target_not_found(service, config):
    service.start(config)
    FakePersistentSession.send_error = ws_mod.TargetNotFoundError("nao encontrado")

    with pytest.raises(TargetNotFoundError):
        service.send(config)


def test_send_maps_message_error(service, config):
    service.start(config)
    FakePersistentSession.send_error = ws_mod.MessageSendError("falha")

    with pytest.raises(SendError):
        service.send(config)


def test_send_maps_closed_session(service, config):
    service.start(config)
    FakePersistentSession.send_error = ws_mod.SessionNotOpenError("fechada")

    with pytest.raises(SessionClosedError):
        service.send(config)

    assert not service.is_open


def test_stop_requires_open_session(service):
    with pytest.raises(SessionClosedError):
        service.stop()


def test_stop_closes_open_session(service, config):
    service.start(config)
    service.stop()

    assert not service.is_open


def test_stop_maps_close_error(service, config):
    service.start(config)
    FakePersistentSession.stop_error = ws_mod.SessionCloseError("falha ao fechar")

    with pytest.raises(SessionStopError):
        service.stop()
