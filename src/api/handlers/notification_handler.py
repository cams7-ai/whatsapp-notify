"""Orquestração HTTP para mensagens e sessão do WhatsApp Web."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from fastapi import Response, status
from fastapi.concurrency import run_in_threadpool

from api.exceptions import ApiError
from api.schemas.notification_schema import (
    NotificationRequest,
    NotificationResponse,
    SendAndCloseNotificationRequest,
    SessionResponse,
)
from config import AppConfig, ConfigError, MissingRequiredValueError, load_config, load_session_config
from domain import (
    AuthenticationError,
    DomainError,
    QRCodeNotFoundError,
    SendError,
    SessionAlreadyOpenError,
    SessionClosedError,
    SessionStartError,
    SessionStopError,
    TargetNotFoundError,
)
from services import WhatsAppNotificationService, WhatsAppSessionService

logger = logging.getLogger(__name__)

class NotificationHandler:
    """Adapta requisições HTTP para os fluxos de aplicação do WhatsApp."""

    def __init__(self, session_service: WhatsAppSessionService | None = None) -> None:
        self._operation_lock = asyncio.Lock()
        self._session_service = session_service or WhatsAppSessionService()

    async def start_session(
        self,
        headless: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> SessionResponse:
        config = self._load_session_config(
            headless=headless,
            timeout_seconds=timeout_seconds,
        )

        try:
            async with self._operation_lock:
                await run_in_threadpool(self._session_service.start, config)
        except Exception as exc:
            self._raise_api_error(exc)

        return SessionResponse(
            status="ok",
            message="Sessão do WhatsApp Web iniciada com sucesso.",
        )

    async def get_qr_code(self) -> Response:
        try:
            async with self._operation_lock:
                qr_code, expires_in_seconds = await run_in_threadpool(
                    self._session_service.capture_qr_code,
                )
        except Exception as exc:
            self._raise_api_error(exc)

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        return Response(
            content=qr_code,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store",
                "X-QRCode-Expires-In-Seconds": str(expires_in_seconds),
                "X-QRCode-Expires-At": expires_at.isoformat(),
            },
        )

    async def send_with_open_session(self, payload: NotificationRequest | None) -> NotificationResponse:
        started_at = time.perf_counter()
        request_payload = payload or NotificationRequest()
        config = self._load_request_config(request_payload)

        logger.info("Requisição recebida para envio em sessão aberta: %s", config.target_name)

        try:
            async with self._operation_lock:
                await run_in_threadpool(self._session_service.send, config)
        except Exception as exc:
            self._raise_api_error(exc)

        return self._notification_response(config=config, started_at=started_at)

    async def stop_session(self) -> SessionResponse:
        try:
            async with self._operation_lock:
                await run_in_threadpool(self._session_service.stop)
        except Exception as exc:
            self._raise_api_error(exc)

        return SessionResponse(
            status="ok",
            message="Sessão do WhatsApp Web encerrada com sucesso.",
        )

    async def send_and_close(
        self,
        payload: SendAndCloseNotificationRequest | None,
    ) -> NotificationResponse:
        started_at = time.perf_counter()
        request_payload = payload or SendAndCloseNotificationRequest()
        config = self._load_request_config(request_payload)

        logger.info("Requisição recebida para envio ao destino: %s", config.target_name)

        try:
            async with self._operation_lock:
                if self._session_service.is_open:
                    await run_in_threadpool(self._session_service.send, config)
                    await run_in_threadpool(self._session_service.stop)
                else:
                    await run_in_threadpool(self._send_message_and_close, config)
        except Exception as exc:
            self._raise_api_error(exc)

        return self._notification_response(config=config, started_at=started_at)

    @staticmethod
    def _load_request_config(payload: NotificationRequest) -> AppConfig:
        try:
            return load_config(
                target_name=payload.target_name,
                message=payload.message,
                headless=getattr(payload, "headless", None),
                timeout_seconds=getattr(payload, "timeout_seconds", None),
            )
        except MissingRequiredValueError as exc:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="DADOS_OBRIGATORIOS_AUSENTES",
                message=str(exc),
                fields=[exc.request_field],
            ) from exc
        except ConfigError as exc:
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="CONFIGURACAO_INVALIDA",
                message=f"Configuração inválida do servidor: {exc}",
            ) from exc

    @staticmethod
    def _load_session_config(
        *,
        headless: bool | None,
        timeout_seconds: int | None = None,
    ) -> AppConfig:
        try:
            return load_session_config(headless=headless, timeout_seconds=timeout_seconds)
        except ConfigError as exc:
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="CONFIGURACAO_INVALIDA",
                message=f"Configuração inválida do servidor: {exc}",
            ) from exc

    def _send_message_and_close(self, config: AppConfig) -> None:
        service = WhatsAppNotificationService(config=config)
        service.send(target_name=config.target_name, message=config.message)

    @staticmethod
    def _notification_response(config: AppConfig, started_at: float) -> NotificationResponse:
        return NotificationResponse(
            status="enviado",
            message="Mensagem enviada com sucesso.",
            contact=config.target_name,
            elapsedTimeInSeconds=round(time.perf_counter() - started_at, 3),
        )

    def _raise_api_error(self, exc: Exception) -> None:
        if isinstance(exc, ApiError):
            raise exc
        if isinstance(exc, SessionAlreadyOpenError):
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="SESSAO_JA_ABERTA",
                message=str(exc),
            ) from exc
        if isinstance(exc, SessionClosedError):
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="SESSAO_FECHADA",
                message=str(exc),
            ) from exc
        if isinstance(exc, TargetNotFoundError):
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="DESTINO_NAO_ENCONTRADO",
                message=str(exc),
                fields=["contact"],
            ) from exc
        if isinstance(exc, QRCodeNotFoundError):
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="QR_CODE_NAO_ENCONTRADO",
                message=str(exc),
            ) from exc
        if isinstance(exc, AuthenticationError):
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="AUTENTICACAO_EXPIRADA",
                message=(
                    f"{exc}. Escaneie o QR Code do WhatsApp Web no navegador aberto "
                    "e tente novamente."
                ),
            ) from exc
        if isinstance(exc, SessionStartError):
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="FALHA_AO_INICIAR_SESSAO",
                message=str(exc),
            ) from exc
        if isinstance(exc, SessionStopError):
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="FALHA_AO_ENCERRAR_SESSAO",
                message=str(exc),
            ) from exc
        if isinstance(exc, SendError):
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="FALHA_NO_ENVIO",
                message=f"Não foi possível confirmar o envio da mensagem: {exc}",
            ) from exc
        if isinstance(exc, DomainError):
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="FALHA_NA_AUTOMACAO",
                message=f"Falha na automação do WhatsApp Web: {exc}",
            ) from exc

        logger.exception("Erro inesperado ao processar requisição")
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="ERRO_INTERNO",
            message="Erro inesperado ao processar a requisição.",
        ) from exc


notification_handler = NotificationHandler()
