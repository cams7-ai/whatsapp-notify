import logging

import pytest

from api.exceptions import ApiError
from api.handlers.notification_handler import NotificationHandler
from api.schemas.notification_schema import NotificationRequest
from domain import SendError, SessionAlreadyOpenError, SessionClosedError


class FakeSessionService:
    def __init__(self):
        self.started = []
        self.sent = []
        self.stopped = 0
        self.start_error = None
        self.send_error = None
        self.stop_error = None

    def start(self, config):
        if self.start_error:
            raise self.start_error
        self.started.append(config)

    def send(self, config):
        if self.send_error:
            raise self.send_error
        self.sent.append(config)

    def stop(self):
        if self.stop_error:
            raise self.stop_error
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
        logger=logging.getLogger("test-handler"),
        session_service=session_service,
    )


@pytest.mark.anyio
async def test_start_session_uses_query_headless(handler, session_service, env):
    response = await handler.start_session(headless=True)

    assert response.status == "ok"
    assert session_service.started[0].headless is True


@pytest.mark.anyio
async def test_start_session_maps_already_open(handler, session_service, env):
    session_service.start_error = SessionAlreadyOpenError("aberta")

    with pytest.raises(ApiError) as error:
        await handler.start_session()

    assert error.value.status_code == 400
    assert error.value.code == "SESSAO_JA_ABERTA"


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
async def test_send_and_close_preserves_complete_send_flow(monkeypatch, handler, env):
    calls = []

    def fake_send_and_close(config):
        calls.append((config.target_name, config.message, config.headless))

    monkeypatch.setattr(handler, "_send_message_and_close", fake_send_and_close)
    payload = NotificationRequest(contact="Grupo", message="Ola", headless=True)

    response = await handler.send_and_close(payload)

    assert response.status == "enviado"
    assert response.target_name == "Grupo"
    assert calls == [("Grupo", "Ola", True)]


@pytest.mark.anyio
async def test_send_and_close_maps_send_error(monkeypatch, handler, env):
    def fake_send_and_close(config):
        raise SendError("falha")

    monkeypatch.setattr(handler, "_send_message_and_close", fake_send_and_close)

    with pytest.raises(ApiError) as error:
        await handler.send_and_close(NotificationRequest(contact="Grupo", message="Ola"))

    assert error.value.status_code == 500
    assert error.value.code == "FALHA_NO_ENVIO"


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
