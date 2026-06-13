from pathlib import Path

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import config as config_module
import services.whatsapp_session_service as session_module
import api.handlers.notification_handler as handler_module
from api.exception_handlers import api_error_handler, unhandled_exception_handler
from api.exceptions import ApiError
from api.handlers.notification_handler import NotificationHandler
from api.server import app, custom_openapi
from config import ConfigError, MissingRequiredValueError, load_config, load_session_config
from domain import (
    AuthenticationError,
    DomainError,
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
    QRCodeNotFoundError as PlaywrightQRCodeNotFoundError,
    SessionAlreadyOpenError as PlaywrightSessionAlreadyOpenError,
    SessionCloseError,
    SessionNotOpenError,
    TargetNotFoundError as PlaywrightTargetNotFoundError,
    WhatsAppNotifyError,
)


@pytest.fixture(autouse=True)
def clean_whatsapp_env(monkeypatch):
    for name in (
        "WHATSAPP_TARGET_NAME",
        "WHATSAPP_MESSAGE",
        "WHATSAPP_HEADLESS",
        "WHATSAPP_PROFILE_DIR",
        "WHATSAPP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_missing_required_value_error_keeps_context():
    error = MissingRequiredValueError("contact", "WHATSAPP_TARGET_NAME")

    assert error.request_field == "contact"
    assert error.env_name == "WHATSAPP_TARGET_NAME"
    assert "WHATSAPP_TARGET_NAME" in str(error)


def test_load_config_uses_environment_and_request_overrides(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.touch()
    monkeypatch.setenv("WHATSAPP_TARGET_NAME", "Env Contact")
    monkeypatch.setenv("WHATSAPP_MESSAGE", "Env Message")
    monkeypatch.setenv("WHATSAPP_HEADLESS", "yes")
    monkeypatch.setenv("WHATSAPP_PROFILE_DIR", "profile")
    monkeypatch.setenv("WHATSAPP_TIMEOUT_SECONDS", "9")

    loaded = load_config(
        env_file,
        target_name=" Request Contact ",
        message=" Request Message ",
        headless=False,
        timeout_seconds=3,
    )

    assert loaded.target_name == "Request Contact"
    assert loaded.message == "Request Message"
    assert loaded.headless is False
    assert loaded.profile_dir == (tmp_path / "profile").resolve()
    assert loaded.timeout_seconds == 3


def test_load_session_config_uses_defaults_when_env_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    loaded = load_session_config(tmp_path / "missing.env")

    assert loaded.target_name == ""
    assert loaded.message == ""
    assert loaded.headless is False
    assert loaded.profile_dir == (tmp_path / ".whatsapp-profile").resolve()
    assert loaded.timeout_seconds == 60


@pytest.mark.parametrize("value", ["1", "true", "yes", "y", "sim", "s"])
def test_load_session_config_parses_true_bool_values(monkeypatch, tmp_path, value):
    monkeypatch.setenv("WHATSAPP_HEADLESS", value)

    assert load_session_config(tmp_path / "missing.env").headless is True


@pytest.mark.parametrize("value", ["0", "false", "no", "n", "nao", "não"])
def test_load_session_config_parses_false_bool_values(monkeypatch, tmp_path, value):
    monkeypatch.setenv("WHATSAPP_HEADLESS", value)

    assert load_session_config(tmp_path / "missing.env").headless is False


def test_load_session_config_rejects_invalid_bool(monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_HEADLESS", "maybe")

    with pytest.raises(ConfigError, match="WHATSAPP_HEADLESS"):
        load_session_config(tmp_path / "missing.env")


@pytest.mark.parametrize("value, message", [("abc", "inteiro"), ("0", "maior que zero")])
def test_load_session_config_rejects_invalid_timeout(monkeypatch, tmp_path, value, message):
    monkeypatch.setenv("WHATSAPP_TIMEOUT_SECONDS", value)

    with pytest.raises(ConfigError, match=message):
        load_session_config(tmp_path / "missing.env")


def test_normalize_optional_text_accepts_none():
    assert config_module._normalize_optional_text(None) is None


def test_request_value_or_required_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TARGET_NAME", raising=False)

    with pytest.raises(MissingRequiredValueError):
        config_module._request_value_or_required_env(
            request_value=None,
            request_field="contact",
            env_name="WHATSAPP_TARGET_NAME",
        )


def test_load_request_config_maps_missing_required_value(monkeypatch):
    def fake_load_config(**kwargs):
        raise MissingRequiredValueError("contact", "WHATSAPP_TARGET_NAME")

    monkeypatch.setattr(handler_module, "load_config", fake_load_config)

    with pytest.raises(ApiError) as error:
        NotificationHandler._load_request_config(
            type("Payload", (), {"target_name": None, "message": None})()
        )

    assert error.value.status_code == 400
    assert error.value.code == "DADOS_OBRIGATORIOS_AUSENTES"


def test_load_request_config_maps_config_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TARGET_NAME", "Contato")
    monkeypatch.setenv("WHATSAPP_MESSAGE", "Mensagem")
    monkeypatch.setenv("WHATSAPP_HEADLESS", "invalid")

    with pytest.raises(ApiError) as error:
        NotificationHandler._load_request_config(
            type("Payload", (), {"target_name": None, "message": None})()
        )

    assert error.value.status_code == 500
    assert error.value.code == "CONFIGURACAO_INVALIDA"


def test_load_session_config_maps_config_error(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TIMEOUT_SECONDS", "-1")

    with pytest.raises(ApiError) as error:
        NotificationHandler._load_session_config(headless=None)

    assert error.value.status_code == 500
    assert error.value.code == "CONFIGURACAO_INVALIDA"


@pytest.mark.parametrize(
    "source, code, status_code",
    [
        (SessionAlreadyOpenError("aberta"), "SESSAO_JA_ABERTA", 400),
        (TargetNotFoundError("destino"), "DESTINO_NAO_ENCONTRADO", 400),
        (AuthenticationError("auth"), "AUTENTICACAO_EXPIRADA", 500),
        (SessionStartError("start"), "FALHA_AO_INICIAR_SESSAO", 500),
        (SessionStopError("stop"), "FALHA_AO_ENCERRAR_SESSAO", 500),
        (SendError("send"), "FALHA_NO_ENVIO", 500),
        (DomainError("domain"), "FALHA_NA_AUTOMACAO", 500),
        (RuntimeError("boom"), "ERRO_INTERNO", 500),
    ],
)
def test_notification_handler_maps_remaining_errors(source, code, status_code):
    handler = NotificationHandler(session_service=object())  # type: ignore[arg-type]

    with pytest.raises(ApiError) as error:
        handler._raise_api_error(source)

    assert error.value.code == code
    assert error.value.status_code == status_code


def test_notification_handler_reraises_api_error():
    handler = NotificationHandler(session_service=object())  # type: ignore[arg-type]
    original = ApiError(status_code=418, code="TEAPOT", message="short")

    with pytest.raises(ApiError) as error:
        handler._raise_api_error(original)

    assert error.value is original


@pytest.mark.anyio
async def test_api_error_handler_and_unhandled_handler():
    api_response = await api_error_handler(
        None,
        ApiError(status_code=400, code="CODIGO", message="mensagem", fields=["field"]),
    )
    unhandled_response = await unhandled_exception_handler(None, RuntimeError("boom"))

    assert api_response.status_code == 400
    assert unhandled_response.status_code == 500


def test_custom_openapi_removes_validation_error_schemas(monkeypatch):
    app.openapi_schema = None
    schema = {
        "paths": {
            "/x": {
                "post": {
                    "responses": {
                        "200": {"description": "ok"},
                        "422": {"description": "validation"},
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "HTTPValidationError": {},
                "ValidationError": {},
                "Kept": {},
            }
        },
    }
    monkeypatch.setattr(app, "original_openapi", lambda: schema)

    generated = custom_openapi()
    cached = custom_openapi()

    assert "422" not in generated["paths"]["/x"]["post"]["responses"]
    assert "HTTPValidationError" not in generated["components"]["schemas"]
    assert "ValidationError" not in generated["components"]["schemas"]
    assert "Kept" in generated["components"]["schemas"]
    assert cached is generated


class FakePersistentSession:
    start_error = None

    def __init__(self, config):
        self.config = config
        self.is_open = False
        self.send_error = None
        self.qr_error = None
        self.stop_error = None

    def start(self):
        if self.start_error:
            raise self.start_error
        self.is_open = True

    def send(self, target_name, message):
        if self.send_error:
            raise self.send_error

    def capture_qr_code(self):
        if self.qr_error:
            raise self.qr_error
        return b"PNG"

    def stop(self):
        if self.stop_error:
            raise self.stop_error
        self.is_open = False


@pytest.fixture
def app_config(tmp_path):
    return config_module.AppConfig(
        target_name="Grupo",
        message="Mensagem",
        headless=True,
        profile_dir=tmp_path,
        timeout_seconds=1,
    )


@pytest.fixture
def patched_session(monkeypatch):
    FakePersistentSession.start_error = None
    monkeypatch.setattr(session_module, "PersistentWhatsAppSession", FakePersistentSession)


@pytest.mark.parametrize(
    "source, expected",
    [
        (PlaywrightSessionAlreadyOpenError("already"), SessionAlreadyOpenError),
        (WhatsAppNotifyError("notify"), SessionStartError),
        (RuntimeError("unexpected"), SessionStartError),
    ],
)
def test_session_start_maps_remaining_errors(patched_session, app_config, source, expected):
    FakePersistentSession.start_error = source
    service = session_module.WhatsAppSessionService()

    with pytest.raises(expected):
        service.start(app_config)


@pytest.mark.parametrize(
    "source, expected",
    [
        (SessionNotOpenError("closed"), SessionClosedError),
        (AuthenticationTimeoutError("auth"), AuthenticationError),
        (PlaywrightTargetNotFoundError("target"), TargetNotFoundError),
        (MessageSendError("send"), SendError),
        (WhatsAppNotifyError("notify"), SendError),
    ],
)
def test_session_send_maps_all_errors(patched_session, app_config, source, expected):
    service = session_module.WhatsAppSessionService()
    service.start(app_config)
    assert service._session is not None
    service._session.send_error = source

    with pytest.raises(expected):
        service.send(app_config)


@pytest.mark.parametrize(
    "source, expected",
    [
        (PlaywrightQRCodeNotFoundError("qr"), QRCodeNotFoundError),
        (AuthenticationTimeoutError("auth"), AuthenticationError),
        (WhatsAppNotifyError("notify"), SessionStartError),
        (RuntimeError("unexpected"), SessionStartError),
    ],
)
def test_session_capture_qr_code_maps_all_errors(patched_session, app_config, source, expected):
    service = session_module.WhatsAppSessionService()
    service.start(app_config)
    assert service._session is not None
    service._session.qr_error = source

    with pytest.raises(expected):
        service.capture_qr_code()


@pytest.mark.parametrize(
    "source, expected",
    [
        (SessionNotOpenError("closed"), SessionClosedError),
        (SessionCloseError("close"), SessionStopError),
        (RuntimeError("unexpected"), SessionStopError),
    ],
)
def test_session_stop_maps_all_errors(patched_session, app_config, source, expected):
    service = session_module.WhatsAppSessionService()
    service.start(app_config)
    assert service._session is not None
    service._session.stop_error = source

    with pytest.raises(expected):
        service.stop()
