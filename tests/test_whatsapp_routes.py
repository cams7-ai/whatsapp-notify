from importlib import import_module

import httpx
import pytest
from fastapi import Response

from api.server import app
from api.schemas.notification_schema import NotificationResponse, SessionResponse

router_module = import_module("api.routers.notification_router")


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
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        start = await client.get("/whatsapp/session/start?headless=true&timeoutInSecounds=15")
        qr_code = await client.get("/whatsapp/session/qrcode")
        send = await client.post("/whatsapp/messages/send", json={"contact": "Grupo", "message": "Olá"})
        stop = await client.get("/whatsapp/session/stop")

    assert start.status_code == 200
    assert start.json()["status"] == "ok"
    assert "charset=utf-8" in start.headers["content-type"]
    assert start.json()["message"] == "sessão iniciada"
    assert fake_handler.headless is True
    assert fake_handler.timeout_seconds == 15
    assert qr_code.status_code == 200
    assert qr_code.content == b"PNG"
    assert qr_code.headers["x-qrcode-expires-in-seconds"] == "60"
    assert send.status_code == 200
    assert send.json()["contact"] == "Grupo"
    assert stop.status_code == 200


@pytest.mark.anyio
async def test_old_notifications_route_is_not_registered():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/notifications", json={"contact": "Grupo", "message": "Olá"})

    assert response.status_code == 404
    assert "charset=utf-8" in response.headers["content-type"]
    assert response.json()["error"]["code"] == "ROTA_NAO_ENCONTRADA"
    assert response.json()["error"]["message"] == "Rota não encontrada."


@pytest.mark.anyio
async def test_send_and_close_route_is_not_registered():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/whatsapp/messages/send-and-close",
            json={"contact": "Grupo", "message": "Olá", "headless": False},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROTA_NAO_ENCONTRADA"


@pytest.mark.anyio
async def test_send_with_open_session_rejects_headless_payload():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/whatsapp/messages/send",
            json={"contact": "Grupo", "message": "Olá", "headless": False},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REQUISICAO_INVALIDA"
    assert "headless" in response.json()["error"]["fields"]
