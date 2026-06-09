"""Excecoes de dominio da aplicacao."""


class DomainError(RuntimeError):
    """Excecao base para erros de dominio."""


class AuthenticationError(DomainError):
    """Excecao quando a autenticacao falha ou expira."""


class TargetNotFoundError(DomainError):
    """Excecao quando o contato ou grupo nao e encontrado."""


class SendError(DomainError):
    """Excecao quando a mensagem nao pode ser enviada."""


class QRCodeNotFoundError(DomainError):
    """Excecao quando o QR Code de autenticacao nao esta disponivel."""


class SessionAlreadyOpenError(DomainError):
    """Excecao quando uma sessao ja esta aberta."""


class SessionClosedError(DomainError):
    """Excecao quando uma operacao exige sessao aberta."""


class SessionStartError(DomainError):
    """Excecao quando nao e possivel abrir a sessao."""


class SessionStopError(DomainError):
    """Excecao quando nao e possivel fechar a sessao."""
