"""Orquestração HTTP para envio de notificações."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import status
from fastapi.concurrency import run_in_threadpool

from api.exceptions import ApiError
from api.schemas.notification_schema import NotificationRequest, NotificationResponse
from config import AppConfig, ConfigError, MissingRequiredValueError, load_config
from domain import AuthenticationError, DomainError, SendError, TargetNotFoundError
from logger import configure_logger
from repositories import NotificationRepository, PlaywrightNotificationRepository
from services import NotificationService


class NotificationHandler:
    """Adapta a requisição HTTP para o fluxo de aplicação."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self._send_lock = asyncio.Lock()

    async def send(self, payload: NotificationRequest | None) -> NotificationResponse:
        started_at = time.perf_counter()
        request_payload = payload or NotificationRequest()
        config = self._load_request_config(request_payload)

        self.logger.info("Requisição recebida para envio ao destino: %s", config.target_name)

        try:
            async with self._send_lock:
                await run_in_threadpool(self._send_message, config)
        except TargetNotFoundError as exc:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="DESTINO_NAO_ENCONTRADO",
                message=str(exc),
                fields=["contact"],
            ) from exc
        except AuthenticationError as exc:
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="AUTENTICACAO_EXPIRADA",
                message=(
                    f"{exc}. Escaneie o QR Code do WhatsApp Web no navegador aberto "
                    "e tente novamente."
                ),
            ) from exc
        except SendError as exc:
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="FALHA_NO_ENVIO",
                message=f"Não foi possível confirmar o envio da mensagem: {exc}",
            ) from exc
        except DomainError as exc:
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="FALHA_NA_AUTOMACAO",
                message=f"Falha na automação do WhatsApp Web: {exc}",
            ) from exc
        except Exception as exc:
            self.logger.exception("Erro inesperado ao processar requisição")
            raise ApiError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="ERRO_INTERNO",
                message="Erro inesperado ao processar a requisição.",
            ) from exc

        return NotificationResponse(
            status="enviado",
            message="Mensagem enviada com sucesso.",
            contact=config.target_name,
            elapsedTimeInSeconds=round(time.perf_counter() - started_at, 3),
        )

    @staticmethod
    def _load_request_config(payload: NotificationRequest) -> AppConfig:
        try:
            return load_config(target_name=payload.target_name, message=payload.message)
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

    def _send_message(self, config: AppConfig) -> None:
        repository: NotificationRepository = PlaywrightNotificationRepository(
            config=config,
            logger=self.logger,
        )
        service = NotificationService(repository=repository, logger=self.logger)
        service.send(target_name=config.target_name, message=config.message)


notification_handler = NotificationHandler(logger=configure_logger())
