import pytest

from config import AppConfig
from domain import (
    AuthenticationError,
    QRCodeNotFoundError,
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
    qr_error = None
    qr_code = b"PNG"

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

    def capture_qr_code(self):
        if self.qr_error:
            raise self.qr_error
        self.is_open = True
        return self.qr_code


@pytest.fixture(autouse=True)
def reset_fake_session(monkeypatch):
    FakePersistentSession.start_error = None
    FakePersistentSession.send_error = None
    FakePersistentSession.stop_error = None
    FakePersistentSession.qr_error = None
    FakePersistentSession.qr_code = b"PNG"
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


def test_capture_qr_code_requires_open_session(service):
    with pytest.raises(SessionClosedError):
        service.capture_qr_code()


def test_capture_qr_code_uses_open_session_and_returns_expiration(service, config):
    service.start(config)

    qr_code, expires_in_seconds = service.capture_qr_code()

    assert qr_code == b"PNG"
    assert expires_in_seconds == 60
    assert service.is_open


def test_capture_qr_code_maps_missing_qr(service, config):
    service.start(config)
    FakePersistentSession.qr_error = ws_mod.QRCodeNotFoundError("sem qr")

    with pytest.raises(QRCodeNotFoundError):
        service.capture_qr_code()


def test_persistent_session_capture_qr_code_uses_short_timeout(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    captured = {}

    def fake_capture_qr_code(self, page, timeout_ms):
        captured["timeout_ms"] = timeout_ms
        return b"PNG"

    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_capture_qr_code",
        fake_capture_qr_code,
    )

    session = whatsapp_module.PersistentWhatsAppSession(config)
    session._page = object()
    session._context = object()
    session._playwright = object()

    assert session.capture_qr_code() == b"PNG"
    assert captured["timeout_ms"] == whatsapp_module.QR_CODE_CAPTURE_TIMEOUT_MS


def test_persistent_session_start_does_not_wait_for_authentication(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    class FakePage:
        def wait_for_timeout(self, timeout):
            pass

    class FakeContext:
        pages = []

        def set_default_timeout(self, timeout):
            pass

        def add_init_script(self, script):
            pass

        def new_page(self):
            return FakePage()

        def close(self):
            pass

    class FakeChromium:
        def launch_persistent_context(self, **kwargs):
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        def stop(self):
            pass

    wait_called = False

    def fake_sync_playwright():
        class Manager:
            def start(self):
                return FakePlaywright()

        return Manager()

    def fake_wait_for_authentication(self, page):
        nonlocal wait_called
        wait_called = True

    monkeypatch.setattr(whatsapp_module, "sync_playwright", fake_sync_playwright)
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_open_whatsapp_web", lambda self, page: None)
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_capture_page_metadata", lambda self, page: None)
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_wait_for_authentication",
        fake_wait_for_authentication,
    )

    session = whatsapp_module.PersistentWhatsAppSession(config)
    session.start()

    assert session.is_open
    assert wait_called is False


def test_persistent_session_send_waits_for_authentication(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    calls = []
    session = whatsapp_module.PersistentWhatsAppSession(config)
    session._page = object()
    session._context = object()
    session._playwright = object()

    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_wait_for_authentication",
        lambda self, page: calls.append("auth"),
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_open_target_conversation",
        lambda self, page: calls.append("target"),
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_send_configured_message",
        lambda self, page: calls.append("send"),
    )

    session.send("Grupo", "Ola")

    assert calls == ["auth", "target", "send"]


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
