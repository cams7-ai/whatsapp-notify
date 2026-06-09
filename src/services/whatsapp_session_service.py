"""Serviço de aplicação para controlar a sessão do WhatsApp Web."""

from __future__ import annotations

import logging

from config import AppConfig
from domain import (
    AuthenticationError,
    QRCodeNotFoundError,
    SendError,
    SessionAlreadyOpenError,
    SessionClosedError,
    SessionStartError,
    SessionStopError,
    TargetNotFoundError,
)
from whatsapp_service import (
    AuthenticationTimeoutError,
    MessageSendError,
    PersistentWhatsAppSession,
    QRCodeNotFoundError as PlaywrightQRCodeNotFoundError,
    SessionAlreadyOpenError as PlaywrightSessionAlreadyOpenError,
    SessionCloseError,
    SessionNotOpenError,
    TargetNotFoundError as PlaywrightTargetNotFoundError,
    WhatsAppNotifyError,
)

logger = logging.getLogger(__name__)

QR_CODE_EXPIRES_IN_SECONDS = 60

class WhatsAppSessionService:
    """Orquestra uma sessão persistente sem expor Playwright para a camada HTTP."""

    def __init__(self) -> None:
        self._session: PersistentWhatsAppSession | None = None

    @property
    def is_open(self) -> bool:
        return self._session is not None and self._session.is_open

    def start(self, config: AppConfig) -> None:
        if self.is_open:
            raise SessionAlreadyOpenError("Já existe uma sessão do WhatsApp Web aberta.")

        session = PersistentWhatsAppSession(config=config)
        try:
            session.start()
        except PlaywrightSessionAlreadyOpenError as exc:
            raise SessionAlreadyOpenError(str(exc)) from exc
        except AuthenticationTimeoutError as exc:
            raise AuthenticationError(str(exc)) from exc
        except WhatsAppNotifyError as exc:
            raise SessionStartError(f"Não foi possível abrir a sessão do WhatsApp Web: {exc}") from exc
        except Exception as exc:
            logger.exception("Erro inesperado ao iniciar sessão do WhatsApp Web")
            raise SessionStartError("Não foi possível abrir a sessão do WhatsApp Web.") from exc

        self._session = session

    def send(self, config: AppConfig) -> None:
        if not self.is_open or self._session is None:
            raise SessionClosedError("A sessão do WhatsApp Web está fechada. Inicie a sessão antes de enviar mensagens.")

        try:
            self._session.send(target_name=config.target_name, message=config.message)
        except SessionNotOpenError as exc:
            self._session = None
            raise SessionClosedError(str(exc)) from exc
        except AuthenticationTimeoutError as exc:
            raise AuthenticationError(str(exc)) from exc
        except PlaywrightTargetNotFoundError as exc:
            raise TargetNotFoundError(str(exc)) from exc
        except MessageSendError as exc:
            raise SendError(str(exc)) from exc
        except WhatsAppNotifyError as exc:
            raise SendError(f"Erro na automação: {exc}") from exc

    def capture_qr_code(self) -> tuple[bytes, int]:
        if not self.is_open or self._session is None:
            raise SessionClosedError("A sessão do WhatsApp Web está fechada. Inicie a sessão antes de enviar mensagens.")

        session = self._session

        try:
            qr_code = session.capture_qr_code()
        except PlaywrightQRCodeNotFoundError as exc:
            raise QRCodeNotFoundError(str(exc)) from exc
        except AuthenticationTimeoutError as exc:
            raise AuthenticationError(str(exc)) from exc
        except WhatsAppNotifyError as exc:
            raise SessionStartError(f"Não foi possível capturar o QR Code do WhatsApp Web: {exc}") from exc
        except Exception as exc:
            logger.exception("Erro inesperado ao capturar QR Code do WhatsApp Web")
            raise SessionStartError("Não foi possível capturar o QR Code do WhatsApp Web.") from exc

        return qr_code, QR_CODE_EXPIRES_IN_SECONDS

    def stop(self) -> None:
        if not self.is_open or self._session is None:
            raise SessionClosedError("A sessão do WhatsApp Web já está fechada.")

        session = self._session
        try:
            session.stop()
        except SessionNotOpenError as exc:
            self._session = None
            raise SessionClosedError(str(exc)) from exc
        except SessionCloseError as exc:
            raise SessionStopError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Erro inesperado ao fechar sessão do WhatsApp Web")
            raise SessionStopError("Não foi possível fechar a sessão do WhatsApp Web.") from exc
        finally:
            if not session.is_open:
                self._session = None
