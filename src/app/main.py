"""API REST do WhatsApp Notify."""

from __future__ import annotations

import asyncio
import os

import uvicorn
from fastapi import Body, FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import AppConfig, ConfigError, MissingRequiredValueError, load_config
from app.logger import configure_logger
from app.whatsapp_service import (
    AuthenticationTimeoutError,
    MessageSendError,
    TargetNotFoundError,
    WhatsAppNotifyError,
    WhatsAppService,
)


logger = configure_logger()
send_lock = asyncio.Lock()

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Verificação simples de disponibilidade da API.",
    },
    {
        "name": "notifications",
        "description": (
            "Envio de mensagens pelo WhatsApp Web usando os dados da requisição "
            "ou as variáveis de ambiente como fallback."
        ),
    },
]

app = FastAPI(
    title="WhatsApp Notify API",
    description="API REST para enviar mensagens pelo WhatsApp Web usando Playwright.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
)


class NotificationRequest(BaseModel):
    """Corpo opcional para sobrescrever o destino e a mensagem do ambiente."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "targetName": "Grupo Teste",
                    "message": "Mensagem enviada pela API",
                },
                {},
            ]
        },
    )

    target_name: str | None = Field(
        default=None,
        alias="targetName",
        description="Nome exato do contato individual ou grupo.",
    )
    message: str | None = Field(
        default=None,
        description="Mensagem que será enviada pelo WhatsApp Web.",
    )


class NotificationResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "status": "enviado",
                    "mensagem": "Mensagem enviada com sucesso.",
                    "targetName": "Grupo Teste",
                }
            ]
        },
    )

    status: str
    mensagem: str
    target_name: str = Field(alias="targetName")


class ErrorDetail(BaseModel):
    codigo: str
    mensagem: str
    campos: list[str] | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "erro": {
                        "codigo": "DADOS_OBRIGATORIOS_AUSENTES",
                        "mensagem": (
                            "Informe 'targetName' no corpo da requisição ou configure "
                            "WHATSAPP_TARGET_NAME no ambiente"
                        ),
                        "campos": ["targetName"],
                    }
                }
            ]
        }
    )

    erro: ErrorDetail


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        fields: list[str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    error: dict[str, str | list[str]] = {
        "codigo": exc.code,
        "mensagem": exc.message,
    }
    if exc.fields:
        error["campos"] = exc.fields

    return JSONResponse(status_code=exc.status_code, content={"erro": error})


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields = _validation_error_fields(exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "erro": {
                "codigo": "REQUISICAO_INVALIDA",
                "mensagem": (
                    "Corpo da requisição inválido. Envie um JSON com os campos "
                    "opcionais 'targetName' e 'message'."
                ),
                "campos": fields,
            }
        },
    )


@app.get(
    "/health",
    summary="Verificar disponibilidade",
    description="Retorna `status: ok` quando a API está disponível.",
    operation_id="healthCheck",
    tags=["health"],
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/notifications",
    response_model=NotificationResponse,
    summary="Enviar mensagem pelo WhatsApp",
    description=(
        "Envia uma mensagem pelo WhatsApp Web. `targetName` e `message` são opcionais; "
        "quando não forem enviados, a API usa `WHATSAPP_TARGET_NAME` e "
        "`WHATSAPP_MESSAGE`."
    ),
    operation_id="sendWhatsAppNotification",
    responses={
        400: {"model": ErrorResponse, "description": "Erro de requisição"},
        500: {"model": ErrorResponse, "description": "Erro interno ou de automação"},
    },
    tags=["notifications"],
)
async def send_notification(
    payload: NotificationRequest | None = Body(default=None),
) -> NotificationResponse:
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
            fields=["targetName"],
        ) from exc
    except AuthenticationTimeoutError as exc:
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="AUTENTICACAO_EXPIRADA",
            message=(
                f"{exc}. Escaneie o QR Code do WhatsApp Web no navegador aberto "
                "e tente novamente."
            ),
        ) from exc
    except MessageSendError as exc:
        raise ApiError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="FALHA_NO_ENVIO",
            message=f"Não foi possível confirmar o envio da mensagem: {exc}",
        ) from exc
    except WhatsAppNotifyError as exc:
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
        mensagem="Mensagem enviada com sucesso.",
        targetName=config.target_name,
    )


def _send_message(config: AppConfig) -> None:
    service = WhatsAppService(config=config, logger=logger)
    service.run()


def _validation_error_fields(exc: RequestValidationError) -> list[str]:
    fields: list[str] = []

    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(str(item) for item in location if item != "body")
        fields.append(field or "body")

    return sorted(set(fields))


def main() -> None:
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
