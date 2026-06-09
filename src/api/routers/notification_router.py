"""Rotas HTTP para controle de sessão e envio de mensagens do WhatsApp."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query

from api.handlers.notification_handler import notification_handler
from api.openapi import BAD_REQUEST_EXAMPLES, INTERNAL_SERVER_ERROR_EXAMPLES
from api.schemas import (
    ErrorResponse,
    NotificationRequest,
    NotificationResponse,
    SendAndCloseNotificationRequest,
    SessionResponse,
)


router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

ERROR_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "Erro de requisição",
        "content": {"application/json": {"examples": BAD_REQUEST_EXAMPLES}},
    },
    500: {
        "model": ErrorResponse,
        "description": "Erro interno ou de automação",
        "content": {"application/json": {"examples": INTERNAL_SERVER_ERROR_EXAMPLES}},
    },
}


@router.get(
    "/session/start",
    response_model=SessionResponse,
    summary="Iniciar sessão do WhatsApp Web",
    description=(
        "Abre o navegador, aguarda autenticação quando necessário e mantém a "
        "sessão do WhatsApp Web ativa para novos envios."
    ),
    operation_id="startWhatsAppSession",
    responses=ERROR_RESPONSES,
)
async def start_whatsapp_session(
    headless: bool | None = Query(default=None),
    timeoutInSecounds: int | None = Query(default=None, gt=0),
) -> SessionResponse:
    return await notification_handler.start_session(
        headless=headless,
        timeout_seconds=timeoutInSecounds,
    )


@router.get(
    "/session/qrcode",
    summary="Capturar QR Code do WhatsApp Web",
    description=(
        "Captura o QR Code visível usando apenas a sessão do WhatsApp Web já "
        "aberta. Se não houver sessão aberta, retorna SESSAO_FECHADA. Os "
        "headers informam a janela estimada de expiração do QR Code."
    ),
    operation_id="getWhatsAppSessionQRCode",
    responses={
        **ERROR_RESPONSES,
        200: {
            "content": {"image/png": {}},
            "description": "Imagem PNG do QR Code.",
        },
    },
)
async def get_whatsapp_session_qrcode():
    return await notification_handler.get_qr_code()


@router.post(
    "/messages/send",
    response_model=NotificationResponse,
    summary="Enviar mensagem usando sessão aberta",
    description=(
        "Envia uma mensagem usando uma sessão do WhatsApp Web já aberta e "
        "autenticada. Não abre nem fecha o navegador."
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
    summary="Encerrar sessão do WhatsApp Web",
    description="Fecha a sessão ativa do WhatsApp Web e o navegador associado.",
    operation_id="stopWhatsAppSession",
    responses=ERROR_RESPONSES,
)
async def stop_whatsapp_session() -> SessionResponse:
    return await notification_handler.stop_session()


@router.post(
    "/messages/send-and-close",
    response_model=NotificationResponse,
    summary="Enviar mensagem e encerrar sessão",
    description=(
        "Se já houver sessão aberta, envia por ela e encerra a sessão. "
        "Caso contrário, abre o WhatsApp Web, autentica quando necessário, "
        "envia a mensagem e fecha o navegador."
    ),
    operation_id="sendWhatsAppMessageAndClose",
    responses=ERROR_RESPONSES,
)
async def send_whatsapp_message_and_close(
    payload: SendAndCloseNotificationRequest | None = Body(default=None),
) -> NotificationResponse:
    return await notification_handler.send_and_close(payload)
