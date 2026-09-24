from importlib import import_module

import pytest
from fastapi import Response

from api.server import app
from api.schemas.notification_schema import NotificationResponse, SessionResponse, SessionStatusResponse

router_module = import_module("api.routers.notification_router")


class ASGIResponse:
    def __init__(self, status_code, headers, content):
        self.status_code = status_code
        self.headers = headers
        self.content = content

    def json(self):
        import json
        return json.loads(self.content)


async def request(method, path, body=None):
    import json
    from urllib.parse import urlsplit

    parsed = urlsplit(path)
    raw_body = b"" if body is None else json.dumps(body).encode()
    messages = iter(({"type": "http.request", "body": raw_body, "more_body": False},))
    started = {}
    content = bytearray()

    async def receive():
        return next(messages)

    async def send(message):
        if message["type"] == "http.response.start":
            started.update(message)
        elif message["type"] == "http.response.body":
            content.extend(message.get("body", b""))

    await app(
        {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1", "method": method, "scheme": "http",
            "path": parsed.path, "raw_path": parsed.path.encode(),
            "query_string": parsed.query.encode(), "root_path": "",
            "headers": [(b"host", b"testserver")]
            + ([] if body is None else [(b"content-type", b"application/json")]),
            "client": ("testclient", 50000), "server": ("testserver", 80),
        }, receive, send,
    )
    headers = {key.decode().lower(): value.decode() for key, value in started["headers"]}
    return ASGIResponse(started["status"], headers, bytes(content))


class FakeRouteHandler:
    async def start_session(self, headless=None, timeout_seconds=None):
        self.timeout_seconds = timeout_seconds
        self.headless = headless
        return SessionResponse(status="ok", message="sessão iniciada")

    async def get_qr_code(self):
        return Response(
            content=b"PNG",
            media_type="image/png",
            headers={
                "x-qrcode-expires-in-seconds": "60",
            },
        )

    async def get_session_status(self):
        return SessionStatusResponse(
            status="SESSAO_FECHADA",
            message="Sessão do WhatsApp Web fechada.",
            isOpen=False,
        )

    async def send_with_open_session(self, payload):
        self.payload = payload
        return NotificationResponse(
            status="enviado",
            message="Mensagem enviada com sucesso.",
            contact=payload.target_name,
            elapsedTimeInSeconds=0.1,
        )

    async def stop_session(self):
        return SessionResponse(status="ok", message="sessão encerrada")


@pytest.mark.anyio
async def test_whatsapp_routes_delegate_to_handler(monkeypatch):
    fake_handler = FakeRouteHandler()
    monkeypatch.setattr(router_module, "notification_handler", fake_handler)
    start = await request("GET", "/whatsapp/session/start?headless=true&timeoutInSecounds=15")
    qr_code = await request("GET", "/whatsapp/session/qrcode")
    session_status = await request("GET", "/whatsapp/session/status")
    send = await request("POST", "/whatsapp/messages/send", {"contact": "Grupo", "message": "Olá"})
    stop = await request("GET", "/whatsapp/session/stop")

    assert start.status_code == 200
    assert start.json()["status"] == "ok"
    assert "charset=utf-8" in start.headers["content-type"]
    assert start.json()["message"] == "sessão iniciada"
    assert fake_handler.headless is True
    assert fake_handler.timeout_seconds == 15
    assert qr_code.status_code == 200
    assert qr_code.content == b"PNG"
    assert qr_code.headers["x-qrcode-expires-in-seconds"] == "60"
    assert session_status.status_code == 200
    assert session_status.json() == {
        "status": "SESSAO_FECHADA",
        "message": "Sessão do WhatsApp Web fechada.",
        "isOpen": False,
    }
    assert send.status_code == 200
    assert send.json()["contact"] == "Grupo"
    assert stop.status_code == 200


@pytest.mark.anyio
async def test_old_notifications_route_is_not_registered():
    response = await request("POST", "/notifications", {"contact": "Grupo", "message": "Olá"})

    assert response.status_code == 404
    assert "charset=utf-8" in response.headers["content-type"]
    assert response.json()["error"]["code"] == "ROTA_NAO_ENCONTRADA"
    assert response.json()["error"]["message"] == "Rota não encontrada."


@pytest.mark.anyio
async def test_send_and_close_route_is_not_registered():
    response = await request(
        "POST", "/whatsapp/messages/send-and-close",
        {"contact": "Grupo", "message": "Olá", "headless": False},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROTA_NAO_ENCONTRADA"


@pytest.mark.anyio
async def test_send_with_open_session_rejects_headless_payload():
    response = await request(
        "POST", "/whatsapp/messages/send",
        {"contact": "Grupo", "message": "Olá", "headless": False},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REQUISICAO_INVALIDA"
    assert "headless" in response.json()["error"]["fields"]
