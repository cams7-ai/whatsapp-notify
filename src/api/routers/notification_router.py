"""Rotas HTTP para controle de sessao e envio de mensagens do WhatsApp."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query

from api.handlers.notification_handler import notification_handler
from api.openapi import BAD_REQUEST_EXAMPLES, INTERNAL_SERVER_ERROR_EXAMPLES
from api.schemas import ErrorResponse, NotificationRequest, NotificationResponse, SessionResponse


router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

ERROR_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "Erro de requisicao",
        "content": {"application/json": {"examples": BAD_REQUEST_EXAMPLES}},
    },
    500: {
        "model": ErrorResponse,
        "description": "Erro interno ou de automacao",
        "content": {"application/json": {"examples": INTERNAL_SERVER_ERROR_EXAMPLES}},
    },
}


@router.get(
    "/session/start",
    response_model=SessionResponse,
    summary="Iniciar sessao do WhatsApp Web",
    description=(
        "Abre o navegador, aguarda autenticacao quando necessario e mantem a "
        "sessao do WhatsApp Web ativa para novos envios."
    ),
    operation_id="startWhatsAppSession",
    responses=ERROR_RESPONSES,
)
async def start_whatsapp_session(
    headless: bool | None = Query(default=None),
) -> SessionResponse:
    return await notification_handler.start_session(headless=headless)


@router.post(
    "/messages/send",
    response_model=NotificationResponse,
    summary="Enviar mensagem usando sessao aberta",
    description=(
        "Envia uma mensagem usando uma sessao do WhatsApp Web ja aberta e "
        "autenticada. Nao abre nem fecha o navegador."
    ),
    operation_id="sendWhatsAppMessage",
    responses=ERROR_RESPONSES,
)
async def send_whatsapp_message(
    payload: NotificationRequest | None = Body(default=None),
) -> NotificationResponse:
    return await notification_handler.send_with_open_session(payload)


@router.get(
    "/session/stop",
    response_model=SessionResponse,
    summary="Encerrar sessao do WhatsApp Web",
    description="Fecha a sessao ativa do WhatsApp Web e o navegador associado.",
    operation_id="stopWhatsAppSession",
    responses=ERROR_RESPONSES,
)
async def stop_whatsapp_session() -> SessionResponse:
    return await notification_handler.stop_session()


@router.post(
    "/messages/send-and-close",
    response_model=NotificationResponse,
    summary="Enviar mensagem e encerrar sessao",
    description=(
        "Mantem o comportamento antigo de POST /notifications: abre o WhatsApp "
        "Web, autentica quando necessario, envia a mensagem e fecha o navegador."
    ),
    operation_id="sendWhatsAppMessageAndClose",
    responses=ERROR_RESPONSES,
)
async def send_whatsapp_message_and_close(
    payload: NotificationRequest | None = Body(default=None),
) -> NotificationResponse:
    return await notification_handler.send_and_close(payload)
