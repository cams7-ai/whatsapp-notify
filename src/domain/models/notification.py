from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Notification:
    """Modelo de domínio para uma notificação de WhatsApp."""

    target_name: str
    message: str

    def __post_init__(self) -> None:
        if not self.target_name or not self.target_name.strip():
            raise ValueError("target_name não pode estar vazio")
        if not self.message or not self.message.strip():
            raise ValueError("message não pode estar vizio")