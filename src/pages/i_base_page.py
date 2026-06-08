from __future__ import annotations
from abc import ABC
import re
import time
from playwright.sync_api import Page, Error as PlaywrightError, Locator

class IBasePage(ABC):
    """Base para todos os POMs do WhatsApp Web."""

    def __init__(self, page: Page) -> None:
        self.page = page

    @staticmethod
    def _normalize_text(value: str) -> str:
        """Normaliza texto removendo caracteres especiais."""
        cleaned = value.replace("\u200B", "").replace("\u00A0", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def _first_visible_locator(
        self,
        selectors: tuple[str, ...],
        timeout_ms: int,
    ) -> Locator | None:
        """Retorna o primeiro seletor visível."""
        deadline = time.monotonic() + (timeout_ms / 1000)

        while time.monotonic() < deadline:
            for selector in selectors:
                locator = self.page.locator(selector).first
                try:
                    if locator.is_visible(timeout=250):
                        return locator
                except PlaywrightError:
                    continue

            self.page.wait_for_timeout(250)

        return None

    def _is_any_selector_visible(
        self,
        selectors: tuple[str, ...],
        timeout_ms: int,
    ) -> bool:
        """Verifica se algum seletor está visível."""
        return self._first_visible_locator(selectors, timeout_ms) is not None