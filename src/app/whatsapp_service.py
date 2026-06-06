"""Serviço de automação do WhatsApp Web com Playwright."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, ViewportSize, sync_playwright

from app.config import AppConfig


WHATSAPP_WEB_URL = "https://web.whatsapp.com"


class WhatsAppNotifyError(RuntimeError):
    """Exceção base para falhas na automação do WhatsApp."""


class AuthenticationTimeoutError(WhatsAppNotifyError):
    """Erro gerado quando a autenticação no WhatsApp Web expira."""


class TargetNotFoundError(WhatsAppNotifyError):
    """Erro gerado quando o contato ou grupo não é encontrado."""


class MessageSendError(WhatsAppNotifyError):
    """Erro gerado quando a mensagem não pode ser enviada."""


class WhatsAppService:
    """Envia a mensagem configurada pelo WhatsApp Web."""

    _authenticated_selectors = (
        '[data-testid="chat-list-search-container"] input[role="textbox"]',
        'input[role="textbox"][data-tab="3"]',
        'input[role="textbox"][aria-label*="Pesquisar" i]',
        'input[role="textbox"][aria-label*="Search" i]',
        '#pane-side [data-testid="chat-list"]',
        '#pane-side div[role="grid"][aria-label*="Lista de conversas" i]',
        '#pane-side div[role="grid"][aria-label*="Chat list" i]',
        '#pane-side input[role="textbox"][data-tab="3"]',
        '#pane-side input[role="textbox"][aria-label*="Pesquisar" i]',
        '#pane-side input[role="textbox"][aria-label*="Search" i]',
        'div[role="textbox"][contenteditable="true"][aria-label*="Search" i]',
        'div[role="textbox"][contenteditable="true"][aria-label*="Pesquisar" i]',
        'div[role="textbox"][contenteditable="true"][aria-label*="Buscar" i]',
        'div[role="textbox"][contenteditable="true"][title*="Search" i]',
        '[data-testid="chat-list-search"]',
        'div[data-testid="chat-list"]',
        'div[aria-label*="Chat list" i]',
        'div[aria-label*="Lista de conversas" i]',
    )

    _qr_code_selectors = (
        'canvas[aria-label*="Scan" i]',
        'canvas[aria-label*="Escanear" i]',
        '[data-testid="qrcode"]',
        "canvas",
    )

    _search_box_selectors = (
        '[data-testid="chat-list-search-container"] input[role="textbox"]',
        'input[role="textbox"][aria-label*="Pesquisar ou começar" i]',
        'input[role="textbox"][aria-label*="Search or start" i]',
        'input[role="textbox"][aria-label*="Pesquisar" i]',
        'input[role="textbox"][aria-label*="Search" i]',
        'input[role="textbox"][aria-label*="Buscar" i]',
        'input[role="textbox"][placeholder*="Pesquisar" i]',
        'input[role="textbox"][placeholder*="Search" i]',
        'input[role="textbox"][placeholder*="Buscar" i]',
        'input[role="textbox"][data-tab="3"]',
        '#pane-side input[role="textbox"][data-tab="3"]',
        '#pane-side input[role="textbox"][aria-label*="Pesquisar" i]',
        '#pane-side input[role="textbox"][aria-label*="Search" i]',
        '#pane-side input[role="textbox"][aria-label*="Buscar" i]',
        '#pane-side input[placeholder*="Pesquisar" i]',
        '#pane-side input[placeholder*="Search" i]',
        '#pane-side input[placeholder*="Buscar" i]',
        'div[role="textbox"][contenteditable="true"][aria-label*="Search" i]',
        'div[role="textbox"][contenteditable="true"][aria-label*="Pesquisar" i]',
        'div[role="textbox"][contenteditable="true"][aria-label*="Buscar" i]',
        'div[role="textbox"][contenteditable="true"][aria-placeholder*="Search" i]',
        'div[role="textbox"][contenteditable="true"][aria-placeholder*="Pesquisar" i]',
        'div[role="textbox"][contenteditable="true"][title*="Search" i]',
        '[data-testid="chat-list-search"] div[contenteditable="true"]',
        '[data-testid="chat-list-search"] input',
        '#pane-side div[role="textbox"][contenteditable="true"]',
        '#side div[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"][data-tab="3"]',
    )

    _message_box_selectors = (
        'footer [data-testid="conversation-compose-box-input"][contenteditable="true"]',
        'div[data-testid="conversation-compose-box-input"][contenteditable="true"]',
        'footer div[role="textbox"][contenteditable="true"][aria-label*="Type a message" i]',
        'footer div[role="textbox"][contenteditable="true"][aria-label*="Digite uma mensagem" i]',
        'footer div[role="textbox"][contenteditable="true"][aria-placeholder*="Type a message" i]',
        'footer div[role="textbox"][contenteditable="true"][aria-placeholder*="Digite uma mensagem" i]',
        'footer div[role="textbox"][contenteditable="true"]',
    )

    _send_button_selectors = (
        'button[aria-label*="Send" i]',
        'button[aria-label*="Enviar" i]',
        'span[data-icon="send"]',
    )

    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.timeout_ms = config.timeout_seconds * 1000

    def run(self) -> None:
        """Abre o WhatsApp Web, autentica se necessário e envia a mensagem."""

        self._ensure_profile_dir(self.config.profile_dir)

        with sync_playwright() as playwright:
            viewport: ViewportSize | None = None
            if self.config.headless:
                viewport = ViewportSize(width=1280, height=900)

            self.logger.info("Inicializando Chromium com perfil persistente")
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.config.profile_dir),
                headless=self.config.headless,
                viewport=viewport,
                args=[] if self.config.headless else ["--start-maximized"],
            )
            context.set_default_timeout(self.timeout_ms)

            try:
                page = context.pages[0] if context.pages else context.new_page()
                self._open_whatsapp_web(page)
                self._wait_for_authentication(page)
                self._open_target_conversation(page)
                self._send_configured_message(page)
            finally:
                self.logger.info("Fechando navegador")
                context.close()

    def _open_whatsapp_web(self, page: Page) -> None:
        self.logger.info("Abrindo %s", WHATSAPP_WEB_URL)
        page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)

    def _wait_for_authentication(self, page: Page) -> None:
        self.logger.info("Verificando autenticação no WhatsApp Web")

        deadline = time.monotonic() + self.config.timeout_seconds
        qr_logged = False

        while time.monotonic() < deadline:
            if self._is_any_selector_visible(page, self._authenticated_selectors, timeout_ms=300):
                self.logger.info("Sessão autenticada")
                return

            if (
                not qr_logged
                and self._is_any_selector_visible(page, self._qr_code_selectors, timeout_ms=300)
            ):
                self.logger.info("QR Code exibido. Escaneie pelo WhatsApp no celular")
                qr_logged = True

            page.wait_for_timeout(1000)

        raise AuthenticationTimeoutError(
            f"Autenticação não concluída em {self.config.timeout_seconds} segundos"
        )

    def _open_target_conversation(self, page: Page) -> None:
        self.logger.info("Buscando contato ou grupo: %s", self.config.target_name)

        search_box = self._first_visible_locator(
            page,
            self._search_box_selectors,
            timeout_ms=self.timeout_ms,
        )
        if search_box is None:
            raise TargetNotFoundError("Campo de busca do WhatsApp Web não encontrado")

        self._fill_textbox(page, search_box, self.config.target_name)

        target = self._find_target_result(page, self.config.target_name)
        if target is None:
            raise TargetNotFoundError(
                f"Contato ou grupo não encontrado: {self.config.target_name}"
            )

        self._click_target_result(target)
        self.logger.info("Conversa aberta: %s", self.config.target_name)

        if self._first_visible_locator(page, self._message_box_selectors, timeout_ms=self.timeout_ms) is None:
            raise TargetNotFoundError("Conversa aberta, mas campo de mensagem não encontrado")

    def _send_configured_message(self, page: Page) -> None:
        self.logger.info("Enviando mensagem")

        message_box = self._first_visible_locator(
            page,
            self._message_box_selectors,
            timeout_ms=self.timeout_ms,
        )
        if message_box is None:
            raise MessageSendError("Campo de mensagem não encontrado")

        self._fill_textbox(page, message_box, self.config.message)

        send_button = self._first_visible_locator(page, self._send_button_selectors, timeout_ms=3000)
        if send_button is not None:
            send_button.click()
        else:
            page.keyboard.press("Enter")

        # Aguardar a mensagem ser enviada verificando dois sinais possíveis:
        # 1) O campo de entrada ficou vazio (texto interno sem espaços/zero-width)
        # 2) Apareceu na conversa uma bolha com o texto exato da mensagem
        deadline = time.monotonic() + self.config.timeout_seconds
        escaped_message = re.escape(self.config.message)
        exact_text = re.compile(rf"^\s*{escaped_message}\s*$", re.IGNORECASE)

        while time.monotonic() < deadline:
            try:
                # Obter texto visível do campo de mensagem, removendo zero-width spaces
                content = message_box.evaluate(
                    "el => (el.innerText || el.textContent || '').replace(/\u200B/g, '').trim()",
                    timeout=250,
                )

                if isinstance(content, str) and content == "":
                    # Campo limpo -> provavelmente enviado
                    break

                # Verificar se a mensagem já apareceu na conversa
                try:
                    candidate = page.get_by_text(exact_text).first
                    if candidate.is_visible(timeout=250):
                        break
                except PlaywrightError:
                    # não encontrou ainda
                    pass
            except PlaywrightError:
                # Se não conseguir avaliar, esperar mais um pouco
                pass

            page.wait_for_timeout(200)

        # Pequena espera extra para garantir processamento no servidor
        page.wait_for_timeout(1000)
        self.logger.info("Mensagem enviada")

    def _find_target_result(self, page: Page, target_name: str) -> Locator | None:
        escaped_target = re.escape(target_name)
        exact_text = re.compile(rf"^\s*{escaped_target}\s*$", re.IGNORECASE)

        candidates = (
            page.locator('#pane-side [data-testid="cell-frame-title"] span[title]').filter(
                has_text=exact_text
            ).first,
            page.locator('[data-testid="cell-frame-title"] span[title]').filter(
                has_text=exact_text
            ).first,
            page.locator('div[role="grid"] span[title]').filter(has_text=exact_text).first,
            page.locator('div[aria-label*="Chat list" i] span[title]').filter(has_text=exact_text).first,
            page.locator('div[aria-label*="Lista de conversas" i] span[title]').filter(
                has_text=exact_text
            ).first,
            page.locator("span[title]").filter(has_text=exact_text).first,
            page.get_by_text(exact_text).first,
        )

        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            for candidate in candidates:
                try:
                    if candidate.is_visible(timeout=300):
                        return candidate
                except PlaywrightError:
                    continue

            page.wait_for_timeout(500)

        return None

    def _click_target_result(self, target: Locator) -> None:
        try:
            row = target.locator(
                'xpath=ancestor::*[@role="listitem" or @role="gridcell"][1]'
            )
            if row.is_visible(timeout=500):
                row.click()
                return
        except PlaywrightError:
            pass

        target.click()

    def _fill_textbox(self, page: Page, locator: Locator, value: str) -> None:
        locator.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        locator.fill(value)

    def _first_visible_locator(
        self,
        page: Page,
        selectors: tuple[str, ...],
        timeout_ms: int,
    ) -> Locator | None:
        deadline = time.monotonic() + (timeout_ms / 1000)

        while time.monotonic() < deadline:
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if locator.is_visible(timeout=250):
                        return locator
                except PlaywrightError:
                    continue

            page.wait_for_timeout(250)

        return None

    def _is_any_selector_visible(
        self,
        page: Page,
        selectors: tuple[str, ...],
        timeout_ms: int,
    ) -> bool:
        return self._first_visible_locator(page, selectors, timeout_ms) is not None

    @staticmethod
    def _ensure_profile_dir(profile_dir: Path) -> None:
        profile_dir.mkdir(parents=True, exist_ok=True)
