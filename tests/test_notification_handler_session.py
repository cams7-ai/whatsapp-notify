import pytest

from api.exceptions import ApiError
from api.handlers.notification_handler import NotificationHandler
from api.schemas.notification_schema import NotificationRequest
from domain import QRCodeNotFoundError, SessionAlreadyOpenError, SessionClosedError

class FakeSessionService:
    def __init__(self):
        self.started = []
        self.sent = []
        self.stopped = 0
        self.is_open = False
        self.qr_code = b"PNG"
        self.qr_expires_in_seconds = 60
        self.qr_error = None
        self.start_error = None
        self.send_error = None
        self.stop_error = None

    def start(self, config):
        if self.start_error:
            raise self.start_error
        self.is_open = True
        self.started.append(config)

    def send(self, config):
        if self.send_error:
            raise self.send_error
        self.sent.append(config)

    def capture_qr_code(self):
        if not self.is_open:
            raise SessionClosedError("A sessão do WhatsApp Web está fechada. Inicie a sessão antes de enviar mensagens.")
        if self.qr_error:
            raise self.qr_error
        return self.qr_code, self.qr_expires_in_seconds

    def stop(self):
        if self.stop_error:
            raise self.stop_error
        self.is_open = False
        self.stopped += 1


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_TARGET_NAME", "Contato Env")
    monkeypatch.setenv("WHATSAPP_MESSAGE", "Mensagem Env")
    monkeypatch.setenv("WHATSAPP_HEADLESS", "false")
    monkeypatch.setenv("WHATSAPP_PROFILE_DIR", str(tmp_path))
    monkeypatch.setenv("WHATSAPP_TIMEOUT_SECONDS", "1")


@pytest.fixture
def session_service():
    return FakeSessionService()


@pytest.fixture
def handler(session_service):
    return NotificationHandler(
        session_service=session_service,
    )


@pytest.mark.anyio
async def test_start_session_uses_query_headless(handler, session_service, env):
    response = await handler.start_session(headless=True)

    assert response.status == "ok"
    assert session_service.started[0].headless is True


@pytest.mark.anyio
async def test_start_session_uses_payload_timeout(handler, session_service, env):
    response = await handler.start_session(timeout_seconds=15)

    assert response.status == "ok"
    assert session_service.started[0].timeout_seconds == 15


@pytest.mark.anyio
async def test_start_session_maps_already_open(handler, session_service, env):
    session_service.start_error = SessionAlreadyOpenError("aberta")

    with pytest.raises(ApiError) as error:
        await handler.start_session()

    assert error.value.status_code == 400
    assert error.value.code == "SESSAO_JA_ABERTA"


@pytest.mark.anyio
async def test_get_qr_code_returns_png_with_expiration_headers(handler, env):
    handler._session_service.is_open = True

    response = await handler.get_qr_code()

    assert response.body == b"PNG"
    assert response.media_type == "image/png"
    assert response.headers["x-qrcode-expires-in-seconds"] == "60"
    assert "x-qrcode-expires-at" in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_get_qr_code_maps_missing_qr(handler, session_service, env):
    session_service.is_open = True
    session_service.qr_error = QRCodeNotFoundError("QR Code não encontrado")

    with pytest.raises(ApiError) as error:
        await handler.get_qr_code()

    assert error.value.status_code == 400
    assert error.value.code == "QR_CODE_NAO_ENCONTRADO"


@pytest.mark.anyio
async def test_get_qr_code_maps_closed_session(handler, env):
    with pytest.raises(ApiError) as error:
        await handler.get_qr_code()

    assert error.value.status_code == 400
    assert error.value.code == "SESSAO_FECHADA"


@pytest.mark.anyio
async def test_send_with_open_session_uses_payload(handler, session_service, env):
    payload = NotificationRequest(contact="Grupo", message="Ola")
    response = await handler.send_with_open_session(payload)

    assert response.status == "enviado"
    assert response.target_name == "Grupo"
    assert session_service.sent[0].target_name == "Grupo"
    assert session_service.sent[0].message == "Ola"


@pytest.mark.anyio
async def test_send_with_open_session_maps_closed_session(handler, session_service, env):
    session_service.send_error = SessionClosedError("fechada")

    with pytest.raises(ApiError) as error:
        await handler.send_with_open_session(NotificationRequest(contact="Grupo", message="Ola"))

    assert error.value.status_code == 400
    assert error.value.code == "SESSAO_FECHADA"


@pytest.mark.anyio
async def test_stop_session(handler, session_service):
    response = await handler.stop_session()

    assert response.status == "ok"
    assert session_service.stopped == 1


@pytest.mark.anyio
async def test_stop_session_maps_closed_session(handler, session_service):
    session_service.stop_error = SessionClosedError("fechada")

    with pytest.raises(ApiError) as error:
        await handler.stop_session()

    assert error.value.status_code == 400
    assert error.value.code == "SESSAO_FECHADA"
