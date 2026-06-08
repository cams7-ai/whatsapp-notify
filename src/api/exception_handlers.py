"""Tratamento centralizado de erros HTTP."""

from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.exceptions import ApiError
from logger import configure_logger


logger = configure_logger()


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        fields=exc.fields,
    )


async def request_validation_error_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return _error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="REQUISICAO_INVALIDA",
        message=(
            "Corpo da requisição inválido. Envie um JSON com os campos "
            "opcionais 'contact' e 'message'."
        ),
        fields=_validation_error_fields(exc),
    )


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _http_error_code_and_message(exc)
    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro inesperado fora do fluxo principal da API")
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="ERRO_INTERNO",
        message="Erro inesperado ao processar a requisição.",
    )


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
