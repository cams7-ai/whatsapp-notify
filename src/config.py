"""Carregamento e validacao das configuracoes do WhatsApp Notify."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Erro gerado quando uma configuracao obrigatoria esta ausente ou invalida."""


class MissingRequiredValueError(ConfigError):
    """Erro gerado quando a requisicao e o ambiente nao fornecem um valor obrigatorio."""

    def __init__(self, request_field: str, env_name: str) -> None:
        self.request_field = request_field
        self.env_name = env_name
        super().__init__(
            f"Informe '{request_field}' no corpo da requisicao ou configure {env_name} no ambiente"
        )


@dataclass(frozen=True)
class AppConfig:
    target_name: str
    message: str
    headless: bool
    profile_dir: Path
    timeout_seconds: int


def load_config(
    env_file: Path | None = None,
    *,
    target_name: str | None = None,
    message: str | None = None,
    headless: bool | None = None,
) -> AppConfig:
    """Carrega configuracoes para um fluxo de envio de mensagem."""

    _, base_dir = _load_environment(env_file)
    return AppConfig(
        target_name=_request_value_or_required_env(
            request_value=target_name,
            request_field="contact",
            env_name="WHATSAPP_TARGET_NAME",
        ),
        message=_request_value_or_required_env(
            request_value=message,
            request_field="message",
            env_name="WHATSAPP_MESSAGE",
        ),
        headless=headless if headless is not None else _parse_bool("WHATSAPP_HEADLESS", default=False),
        profile_dir=_parse_profile_dir("WHATSAPP_PROFILE_DIR", base_dir),
        timeout_seconds=_parse_positive_int("WHATSAPP_TIMEOUT_SECONDS", default=60),
    )


def load_session_config(
    env_file: Path | None = None,
    *,
    headless: bool | None = None,
) -> AppConfig:
    """Carrega configuracoes para abrir uma sessao sem exigir contato ou mensagem."""

    _, base_dir = _load_environment(env_file)
    return AppConfig(
        target_name="",
        message="",
        headless=headless if headless is not None else _parse_bool("WHATSAPP_HEADLESS", default=False),
        profile_dir=_parse_profile_dir("WHATSAPP_PROFILE_DIR", base_dir),
        timeout_seconds=_parse_positive_int("WHATSAPP_TIMEOUT_SECONDS", default=60),
    )


def _load_environment(env_file: Path | None) -> tuple[Path, Path]:
    env_path = env_file or Path.cwd() / ".env"
    base_dir = env_path.parent if env_path.exists() else Path.cwd()

    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    return env_path, base_dir


def _request_value_or_required_env(
    *,
    request_value: str | None,
    request_field: str,
    env_name: str,
) -> str:
    normalized_request_value = _normalize_optional_text(request_value)
    if normalized_request_value is not None:
        return normalized_request_value

    env_value = _normalize_optional_text(os.getenv(env_name))
    if env_value is None:
        raise MissingRequiredValueError(request_field=request_field, env_name=env_name)

    return env_value


def _parse_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "sim", "s"}:
        return True
    if normalized in {"0", "false", "no", "n", "nao", "não"}:
        return False

    raise ConfigError(
        f"Valor invalido para {name}: use true/false, yes/no, sim/nao ou 1/0"
    )


def _parse_profile_dir(name: str, base_dir: Path) -> Path:
    value = os.getenv(name, ".whatsapp-profile").strip() or ".whatsapp-profile"
    profile_dir = Path(value)

    if not profile_dir.is_absolute():
        profile_dir = base_dir / profile_dir

    return profile_dir.resolve()


def _parse_positive_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ConfigError(f"Valor invalido para {name}: informe um numero inteiro") from exc

    if parsed <= 0:
        raise ConfigError(f"Valor invalido para {name}: informe um numero maior que zero")

    return parsed


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None
