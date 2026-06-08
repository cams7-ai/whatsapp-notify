"""API REST do WhatsApp Notify."""

from __future__ import annotations

import asyncio
import time

from fastapi import Body, FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import AppConfig, ConfigError, MissingRequiredValueError, load_config
from logger import configure_logger
from repositories import NotificationRepository, PlaywrightNotificationRepository
from services import NotificationService
from domain import (
    AuthenticationError,
    DomainError,
    SendError,
    TargetNotFoundError,
)


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

OPENAPI_TAGS = [
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
        json_schema_extra={
            "examples": [
                {
                    "contact": "Grupo Teste",
                    "message": "Mensagem enviada pela API",
                },
                {},
            ]
        },
    )

    target_name: str | None = Field(
        default=None,
        alias="contact",
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
                    "message": "Mensagem enviada com sucesso.",
                    "contact": "Grupo Teste",
                    "elapsedTimeInSeconds": 12.345,
                }
            ]
        },
    )

    status: str
    message: str
    target_name: str = Field(alias="contact")
    elapsed_seconds: float = Field(
        alias="elapsedTimeInSeconds",
        description="Tempo total decorrido, em segundos, até confirmar o envio.",
    )


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[str] | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "DADOS_OBRIGATORIOS_AUSENTES",
                        "message": (
                            "Informe 'contact' no corpo da requisição ou configure "
                            "WHATSAPP_TARGET_NAME no ambiente"
                        ),
                        "fields": ["contact"],
                    }
                }
            ]
        }
    )

    error: ErrorDetail


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


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    fields: list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, str | list[str]] = {
        "code": code,
        "message": message,
    }
    if fields:
        error["fields"] = fields

    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers=headers,
    )


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        fields=exc.fields,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="REQUISICAO_INVALIDA",
        message=(
            "Corpo da requisi??o inv?lido. Envie um JSON com os campos "
            "opcionais 'contact' e 'message'."
        ),
        fields=_validation_error_fields(exc),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _http_error_code_and_message(exc)
    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro inesperado fora do fluxo principal da API")
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="ERRO_INTERNO",
        message="Erro inesperado ao processar a requisi??o.",
    )


@app.post(
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


def _http_error_code_and_message(exc: StarletteHTTPException) -> tuple[str, str]:
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return "ROTA_NAO_ENCONTRADA", "Rota não encontrada."

    if exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
        return "METODO_NAO_PERMITIDO", "Método HTTP não permitido para esta rota."

    if 400 <= exc.status_code < 500:
        detail = exc.detail if isinstance(exc.detail, str) else "Erro na requisição."
        return "ERRO_NA_REQUISICAO", detail

    detail = exc.detail if isinstance(exc.detail, str) else "Erro inesperado ao processar a requisição."
    return "ERRO_INTERNO", detail


def _validation_error_fields(exc: RequestValidationError) -> list[str]:
    fields: list[str] = []

    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(
            str(item)
            for item in location
            if item != "body" and not isinstance(item, int)
        )
        fields.append(field or "body")

    return sorted(set(fields))


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )

    for path_item in openapi_schema.get("paths", {}).values():
        for operation in path_item.values():
            responses = operation.get("responses")
            if isinstance(responses, dict):
                responses.pop("422", None)

    schemas = openapi_schema.get("components", {}).get("schemas", {})
    if isinstance(schemas, dict):
        schemas.pop("HTTPValidationError", None)
        schemas.pop("ValidationError", None)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
