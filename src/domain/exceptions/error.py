
class DomainError(RuntimeError):
    """Exceção base para erros de domínio."""


class NotificationError(DomainError):
    """Exceção para erros gerais no processamento de notificações."""


class AuthenticationError(DomainError):
    """Exceção quando a autenticação falha ou expira."""


class TargetNotFoundError(DomainError):
    """Exceção quando o contato/grupo não é encontrado."""


class SendError(DomainError):
    """Exceção quando a mensagem não pode ser enviada."""
