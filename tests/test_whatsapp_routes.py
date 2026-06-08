from importlib import import_module

from fastapi.testclient import TestClient

from api.server import app
from api.schemas.notification_schema import NotificationResponse, SessionResponse

router_module = import_module("api.routers.notification_router")


class FakeRouteHandler:
    async def start_session(self, headless=None):
        self.headless = headless
        return SessionResponse(status="ok", message="sessao iniciada")

    async def send_with_open_session(self, payload):
        self.payload = payload
        return NotificationResponse(
            status="enviado",
            message="Mensagem enviada com sucesso.",
            contact=payload.target_name,
            elapsedTimeInSeconds=0.1,
        )

    async def stop_session(self):
        return SessionResponse(status="ok", message="sessao encerrada")

    async def send_and_close(self, payload):
        self.payload = payload
        return NotificationResponse(
            status="enviado",
            message="Mensagem enviada com sucesso.",
            contact=payload.target_name,
            elapsedTimeInSeconds=0.2,
        )


def test_whatsapp_routes_delegate_to_handler(monkeypatch):
    fake_handler = FakeRouteHandler()
    monkeypatch.setattr(router_module, "notification_handler", fake_handler)
    client = TestClient(app, raise_server_exceptions=False)

    start = client.get("/whatsapp/session/start?headless=true")
    send = client.post("/whatsapp/messages/send", json={"contact": "Grupo", "message": "Ola"})
    stop = client.get("/whatsapp/session/stop")
    send_and_close = client.post(
        "/whatsapp/messages/send-and-close",
        json={"contact": "Grupo", "message": "Ola", "headless": False},
    )

    assert start.status_code == 200
    assert start.json()["status"] == "ok"
    assert fake_handler.headless is True
    assert send.status_code == 200
    assert send.json()["contact"] == "Grupo"
    assert stop.status_code == 200
    assert send_and_close.status_code == 200
    assert send_and_close.json()["elapsedTimeInSeconds"] == 0.2


def test_old_notifications_route_is_not_registered():
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/notifications", json={"contact": "Grupo", "message": "Ola"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROTA_NAO_ENCONTRADA"
