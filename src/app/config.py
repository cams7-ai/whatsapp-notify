"""Carregamento e validação das configurações do WhatsApp Notify."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Erro gerado quando uma configuração obrigatória está ausente ou inválida."""


@dataclass(frozen=True)
class AppConfig:
    target_name: str
    message: str
    headless: bool
    profile_dir: Path
    timeout_seconds: int


def load_config(env_file: Path | None = None) -> AppConfig:
    """Carrega o arquivo .env e processa as variáveis de ambiente."""

    env_path = env_file or Path.cwd() / ".env"
    base_dir = env_path.parent if env_path.exists() else Path.cwd()

    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    target_name = _required_env("WHATSAPP_TARGET_NAME")
    message = _required_env("WHATSAPP_MESSAGE")
    headless = _parse_bool("WHATSAPP_HEADLESS", default=False)
    profile_dir = _parse_profile_dir("WHATSAPP_PROFILE_DIR", base_dir)
    timeout_seconds = _parse_positive_int("WHATSAPP_TIMEOUT_SECONDS", default=60)

    return AppConfig(
        target_name=target_name,
        message=message,
        headless=headless,
        profile_dir=profile_dir,
        timeout_seconds=timeout_seconds,
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigError(f"Variável obrigatória ausente: {name}")
    return value.strip()


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
        f"Valor inválido para {name}: use true/false, yes/no, sim/não ou 1/0"
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
        raise ConfigError(f"Valor inválido para {name}: informe um número inteiro") from exc

    if parsed <= 0:
        raise ConfigError(f"Valor inválido para {name}: informe um número maior que zero")

    return parsed
