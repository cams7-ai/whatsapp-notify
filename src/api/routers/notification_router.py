
from __future__ import annotations
import time
import asyncio
from fastapi import APIRouter, Body, status
from fastapi.concurrency import run_in_threadpool
from config import AppConfig, ConfigError, MissingRequiredValueError, load_config
from logger import configure_logger
from api.exceptions import ApiError
from api.schemas.error_schema import ErrorResponse
from api.schemas.notification_schema import NotificationRequest, NotificationResponse
from domain import (
    AuthenticationError,
    DomainError,
    SendError,
    TargetNotFoundError,
)
from repositories import NotificationRepository, PlaywrightNotificationRepository
from services import NotificationService

logger = configure_logger()
send_lock = asyncio.Lock()

BAD_REQUEST_EXAMPLES = {
    "invalidRequest": {
        "summary": "Corpo inválido",
        "value": {
            "error": {
                "code": "REQUISICAO_INVALIDA",
                "message": (
                    "Corpo da requisição inválido. Envie um JSON com os campos "
                    "opcionais 'contact' e 'message'."
                ),
                "fields": ["message"],
            }
        },
    },
    "missingRequiredValue": {
        "summary": "Campo efetivo ausente",
        "value": {
            "error": {
                "code": "DADOS_OBRIGATORIOS_AUSENTES",
                "message": (
                    "Informe 'contact' no corpo da requisição ou configure "
                    "WHATSAPP_TARGET_NAME no ambiente"
                ),
                "fields": ["contact"],
            }
        },
    },
    "contactNotFound": {
        "summary": "Contato ou grupo não encontrado",
        "value": {
            "error": {
                "code": "DESTINO_NAO_ENCONTRADO",
                "message": "Contato ou grupo não encontrado: Grupo Teste",
                "fields": ["contact"],
            }
        },
    },
}

INTERNAL_SERVER_ERROR_EXAMPLES = {
    "invalidConfiguration": {
        "summary": "Configuração inválida",
        "value": {
            "error": {
                "code": "CONFIGURACAO_INVALIDA",
                "message": (
                    "Configuração inválida do servidor: Valor inválido para "
                    "WHATSAPP_TIMEOUT_SECONDS: informe um número inteiro"
                ),
            }
        },
    },
    "authenticationExpired": {
        "summary": "Timeout de autenticação",
        "value": {
            "error": {
                "code": "AUTENTICACAO_EXPIRADA",
                "message": (
                    "Autenticação não concluída em 60 segundos. Escaneie o QR Code "
                    "do WhatsApp Web no navegador aberto e tente novamente."
                ),
            }
        },
    },
    "sendFailure": {
        "summary": "Falha no envio",
        "value": {
            "error": {
                "code": "FALHA_NO_ENVIO",
                "message": (
                    "Não foi possível confirmar o envio da mensagem: Mensagem não "
                    "foi confirmada pelo WhatsApp Web. Status detectado: pendente."
                ),
            }
        },
    },
    "internalError": {
        "summary": "Erro inesperado",
        "value": {
            "error": {
                "code": "ERRO_INTERNO",
                "message": "Erro inesperado ao processar a requisição.",
            }
        },
    },
}

router = APIRouter(prefix="", tags=["notifications"])

@router.post(
    "/notifications",
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
    tags=["notifications"],
)
async def send_notification(
    payload: NotificationRequest | None = Body(default=None),
) -> NotificationResponse:
    started_at = time.perf_counter()
    request_payload = payload or NotificationRequest()

    try:
        config = load_config(
            target_name=request_payload.target_name,
            message=request_payload.message,
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

    logger.info("Requisição recebida para envio ao destino: %s", config.target_name)

    try:
        async with send_lock:
            await run_in_threadpool(_send_message, config)
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
        logger.exception("Erro inesperado ao processar requisição")
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

def _send_message(config: AppConfig) -> None:
    # Injeção de dependência manual (pode ser substituída por dependency-injector)
    repository: NotificationRepository = PlaywrightNotificationRepository(
        config=config,
        logger=logger,
    )
    service = NotificationService(repository=repository, logger=logger)

    # Delegação ao serviço
    service.send(
        target_name=config.target_name,
        message=config.message,
    )
