"""Rotas HTTP para notificações."""

from __future__ import annotations

from fastapi import APIRouter, Body

from api.handlers.notification_handler import notification_handler
from api.openapi import BAD_REQUEST_EXAMPLES, INTERNAL_SERVER_ERROR_EXAMPLES
from api.schemas import ErrorResponse, NotificationRequest, NotificationResponse


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post(
    "",
    response_model=NotificationResponse,
    summary="Enviar mensagem pelo WhatsApp",
    description=(
        "Envia uma mensagem pelo WhatsApp Web. `contact` e `message` são opcionais; "
        "quando não forem enviados, a API usa `WHATSAPP_TARGET_NAME` e "
        "`WHATSAPP_MESSAGE`."
    ),
    operation_id="sendWhatsAppNotification",
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Erro de requisição",
            "content": {
                "application/json": {
                    "examples": BAD_REQUEST_EXAMPLES,
                }
            },
        },
        500: {
            "model": ErrorResponse,
            "description": "Erro interno ou de automação",
            "content": {
                "application/json": {
                    "examples": INTERNAL_SERVER_ERROR_EXAMPLES,
                }
            },
        },
    },
)
async def send_notification(
    payload: NotificationRequest | None = Body(default=None),
) -> NotificationResponse:
    return await notification_handler.send(payload)
