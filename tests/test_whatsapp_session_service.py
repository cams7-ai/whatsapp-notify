import pytest

from config import AppConfig
from domain import (
    AuthenticationError,
    QRCodeNotFoundError,
    SendError,
    SessionAlreadyOpenError,
    SessionClosedError,
    SessionStartError,
    SessionStatus,
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
    status_result = SessionStatus.SESSAO_ABERTA

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

    def get_status(self):
        return self.status_result


@pytest.fixture(autouse=True)
def reset_fake_session(monkeypatch):
    FakePersistentSession.start_error = None
    FakePersistentSession.send_error = None
    FakePersistentSession.stop_error = None
    FakePersistentSession.qr_error = None
    FakePersistentSession.qr_code = b"PNG"
    FakePersistentSession.status_result = SessionStatus.SESSAO_ABERTA
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


def test_status_returns_closed_before_start(service):
    assert service.status() == SessionStatus.SESSAO_FECHADA


def test_status_delegates_to_open_persistent_session(service, config):
    FakePersistentSession.status_result = SessionStatus.AGUARDANDO_AUTENTICACAO
    service.start(config)

    assert service.status() == SessionStatus.AGUARDANDO_AUTENTICACAO


def test_status_clears_closed_persistent_session(service, config):
    service.start(config)
    service._session.is_open = False

    assert service.status() == SessionStatus.SESSAO_FECHADA
    assert service._session is None


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


def test_persistent_session_status_returns_closed_without_page(config):
    import whatsapp_service as whatsapp_module

    session = whatsapp_module.PersistentWhatsAppSession(config)

    assert session.get_status() == SessionStatus.SESSAO_FECHADA


def test_persistent_session_status_delegates_to_service(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    session = whatsapp_module.PersistentWhatsAppSession(config)
    session._page = object()
    session._context = object()
    session._playwright = object()

    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "get_session_status",
        lambda self, page: SessionStatus.SESSAO_ABERTA,
    )

    assert session.get_status() == SessionStatus.SESSAO_ABERTA


def test_whatsapp_service_status_identifies_qr_code(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    service = whatsapp_module.WhatsAppService(config)

    def fake_visible(page, selectors, timeout_ms):
        return selectors == service._qr_code_selectors

    monkeypatch.setattr(service, "_is_any_selector_visible", fake_visible)
    monkeypatch.setattr(service, "_is_loading_chats_visible", lambda page: False)

    assert service.get_session_status(object()) == SessionStatus.AGUARDANDO_AUTENTICACAO


def test_whatsapp_service_status_identifies_authenticated_screen(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    service = whatsapp_module.WhatsAppService(config)

    def fake_visible(page, selectors, timeout_ms):
        return selectors == service._authenticated_selectors

    monkeypatch.setattr(service, "_is_any_selector_visible", fake_visible)
    monkeypatch.setattr(service, "_is_loading_chats_visible", lambda page: False)

    assert service.get_session_status(object()) == SessionStatus.SESSAO_ABERTA


def test_whatsapp_service_status_identifies_loading_chats(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    service = whatsapp_module.WhatsAppService(config)
    monkeypatch.setattr(service, "_is_any_selector_visible", lambda page, selectors, timeout_ms: False)
    monkeypatch.setattr(service, "_is_loading_chats_visible", lambda page: True)

    assert service.get_session_status(object()) == SessionStatus.CARREGANDO_CONVERSAS


def test_persistent_session_status_does_not_call_mutating_flows(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    forbidden = (
        "_wait_for_authentication",
        "_open_target_conversation",
        "_send_configured_message",
        "_capture_qr_code",
    )
    for name in forbidden:
        monkeypatch.setattr(
            whatsapp_module.WhatsAppService,
            name,
            lambda *args, **kwargs: pytest.fail("mutating flow called"),
        )

    session = whatsapp_module.PersistentWhatsAppSession(config)
    session._page = object()
    session._context = object()
    session._playwright = object()
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "get_session_status",
        lambda self, page: SessionStatus.INICIANDO_SESSAO,
    )

    assert session.get_status() == SessionStatus.INICIANDO_SESSAO


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


def test_open_target_conversation_dismisses_overlays_before_search(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    calls = []
    service = whatsapp_module.WhatsAppService(config)
    search_box = object()
    target = object()
    message_box = object()

    def fake_first_visible_locator(self, page, selectors, timeout_ms):
        calls.append(("first_visible", selectors))
        if selectors == self._search_box_selectors:
            return search_box
        if selectors == self._message_box_selectors:
            return message_box
        return None

    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_dismiss_blocking_overlays",
        lambda self, page: calls.append(("dismiss", None)),
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_first_visible_locator",
        fake_first_visible_locator,
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_fill_textbox",
        lambda self, page, locator, value: calls.append(("fill", locator)),
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_find_target_result",
        lambda self, page, target_name: target,
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_click_target_result",
        lambda self, found_target: calls.append(("click_target", found_target)),
    )

    service._open_target_conversation(object())

    assert calls == [
        ("dismiss", None),
        ("first_visible", service._search_box_selectors),
        ("fill", search_box),
        ("click_target", target),
        ("first_visible", service._message_box_selectors),
    ]


def test_send_configured_message_dismisses_overlays_before_message_box(monkeypatch, config):
    import whatsapp_service as whatsapp_module

    calls = []
    service = whatsapp_module.WhatsAppService(config)
    message_box = object()
    send_button = object()

    def fake_first_visible_locator(self, page, selectors, timeout_ms):
        calls.append(("first_visible", selectors))
        if selectors == self._message_box_selectors:
            return message_box
        if selectors == self._send_button_selectors:
            return send_button
        return None

    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_dismiss_blocking_overlays",
        lambda self, page: calls.append(("dismiss", None)),
    )
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_first_visible_locator",
        fake_first_visible_locator,
    )
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_scroll_conversation_to_bottom", lambda self, page: None)
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_wait_for_outgoing_messages_to_stabilize",
        lambda self, page: None,
    )
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_count_outgoing_message_bubbles", lambda self, page: 0)
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_outgoing_message_keys", lambda self, page: set())
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_fill_message_box", lambda self, page, locator, value: True)
    monkeypatch.setattr(
        whatsapp_module.WhatsAppService,
        "_click_send_button",
        lambda self, locator: calls.append(("click_send", locator)),
    )
    monkeypatch.setattr(whatsapp_module.WhatsAppService, "_wait_for_send_confirmation", lambda *args, **kwargs: True)

    class FakeKeyboard:
        def press(self, key):
            calls.append(("press", key))

    class FakePage:
        keyboard = FakeKeyboard()

        def wait_for_timeout(self, timeout):
            pass

    service._send_configured_message(FakePage())

    assert calls[0] == ("dismiss", None)
    assert calls[1] == ("first_visible", service._message_box_selectors)


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
