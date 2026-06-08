"""Respostas HTTP padronizadas da API."""

from __future__ import annotations

from fastapi.responses import JSONResponse


class Utf8JSONResponse(JSONResponse):
    """Resposta JSON com codificacao UTF-8 explicita no Content-Type."""

    media_type = "application/json; charset=utf-8"
