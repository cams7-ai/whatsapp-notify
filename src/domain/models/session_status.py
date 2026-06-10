from __future__ import annotations

from enum import Enum


class SessionStatus(str, Enum):
    SESSAO_FECHADA = "SESSAO_FECHADA"
    INICIANDO_SESSAO = "INICIANDO_SESSAO"
    AGUARDANDO_AUTENTICACAO = "AGUARDANDO_AUTENTICACAO"
    CARREGANDO_CONVERSAS = "CARREGANDO_CONVERSAS"
    SESSAO_ABERTA = "SESSAO_ABERTA"

    @property
    def message(self) -> str:
        return _SESSION_STATUS_MESSAGES[self]


_SESSION_STATUS_MESSAGES = {
    SessionStatus.SESSAO_FECHADA: "Sess\u00e3o do WhatsApp Web fechada.",
    SessionStatus.INICIANDO_SESSAO: "Sess\u00e3o do WhatsApp Web iniciando.",
    SessionStatus.AGUARDANDO_AUTENTICACAO: "Aguardando autentica\u00e7\u00e3o do WhatsApp Web.",
    SessionStatus.CARREGANDO_CONVERSAS: "Carregando conversas do WhatsApp Web.",
    SessionStatus.SESSAO_ABERTA: "Sess\u00e3o do WhatsApp Web aberta.",
}
