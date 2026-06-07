"""Serviço de automação do WhatsApp Web com Playwright."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, ViewportSize, sync_playwright

from config import AppConfig


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
        'footer button[aria-label*="Send" i][aria-disabled="false"]',
        'footer button[aria-label*="Enviar" i][aria-disabled="false"]',
        'button[data-tab="11"][aria-label*="Send" i][aria-disabled="false"]',
        'button[data-tab="11"][aria-label*="Enviar" i][aria-disabled="false"]',
        'span[data-icon="send"]',
    )

    _outgoing_message_selectors = (
        '[data-testid="conversation-panel-messages"] [data-testid^="conv-msg-"]:has([data-testid="tail-out"])',
        '[data-testid="conversation-panel-messages"] [data-testid="msg-container"]:has([data-testid="tail-out"])',
        '[data-testid^="conv-msg-"]:has([data-testid="tail-out"])',
        '[data-testid="msg-container"]:has([data-testid="tail-out"])',
        '[data-testid^="conv-msg-"]:has([data-testid="tail-out"]) [data-testid="msg-container"]',
        'div.message-out',
        'div[class*="message-out"]',
        'div[role="row"]:has([data-testid="tail-out"])',
        'div[role="row"]:has([data-icon="msg-check"])',
        'div[role="row"]:has([data-icon="msg-dblcheck"])',
        'div[role="row"]:has([data-icon="msg-dblcheck-ack"])',
    )

    _conversation_messages_selectors = (
        '[data-testid="conversation-panel-messages"]',
        '[data-scrolltracepolicy="wa.web.conversation.messages"]',
        '#main [data-tab="8"]',
    )

    _sent_status_selectors = (
        '[data-icon="msg-check"]',
        '[data-icon="msg-dblcheck"]',
        '[data-icon="msg-dblcheck-ack"]',
        '[aria-label*="Enviado" i]',
        '[aria-label*="Enviada" i]',
        '[aria-label*="Entregue" i]',
        '[aria-label*="Lida" i]',
        '[aria-label*="Sent" i]',
        '[aria-label*="Delivered" i]',
        '[aria-label*="Read" i]',
        'title:has-text("wds-ic-check")',
        'title:has-text("wds-ic-read")',
        'title:has-text("wds-ic-delivered")',
    )

    _pending_status_selectors = (
        '[data-icon="msg-time"]',
        '[aria-label*="Enviando" i]',
        '[aria-label*="Pendente" i]',
        '[aria-label*="Sending" i]',
        '[aria-label*="Pending" i]',
        'title:has-text("wds-ic-clock")',
    )

    _failed_status_selectors = (
        '[data-icon="msg-error"]',
        '[data-icon="msg-alert"]',
        '[aria-label*="Falha" i]',
        '[aria-label*="Erro" i]',
        '[aria-label*="Failed" i]',
        '[aria-label*="Error" i]',
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
            # Ajuste de flags para reduzir sinais óbvios de automação quando
            # executando em headless. Mantemos comportamento original em modo
            # visível.
            launch_args: list[str]
            if self.config.headless:
                launch_args = [
                    "--disable-infobars",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--window-size=1280,900",
                ]
            else:
                launch_args = ["--start-maximized"]

            # Define user agent and locale to make headless context behave
            # more like a normal browser session. These values aren't used
            # when running in headful mode by default, but setting them in
            # headless can help avoid detection differences.
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
            locale = "pt-BR"

            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.config.profile_dir),
                headless=self.config.headless,
                viewport=viewport,
                args=launch_args,
                user_agent=user_agent,
                locale=locale,
            )
            # Injeta um script de inicialização para minimizar sinais de
            # automação (navigator.webdriver etc.). Nem sempre é possível
            # injetar (depende da versão), então protegemos com try/except.
            try:
                context.add_init_script(
                    """
                    try {
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        window.chrome = window.chrome || {};
                        Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                    } catch (e) {
                        // ignore
                    }
                    """
                )
            except Exception:
                self.logger.debug("Não foi possível injetar init script no contexto")
            context.set_default_timeout(self.timeout_ms)

            try:
                page = context.pages[0] if context.pages else context.new_page()
                self._open_whatsapp_web(page)
                # Pequeno delay para garantir que dados de sessão e scripts do
                # profile foram carregados antes de coletarmos diagnósticos.
                page.wait_for_timeout(1000)
                # Capture metadata da página para diagnóstico (userAgent,
                # webdriver, url, title, cookies count). Isso ajuda a entender
                # diferenças entre headful e headless quando a sessão não é
                # corretamente reaplicada.
                try:
                    self._capture_page_metadata(page)
                except Exception:
                    self.logger.exception("Falha ao capturar metadata da página")
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

                # Em headless, tentamos capturar o QR Code em arquivo para que
                # o usuário possa escaneá-lo externamente.
                if self.config.headless:
                    try:
                        qr_locator = self._first_visible_locator(page, self._qr_code_selectors, timeout_ms=500)
                        if qr_locator is not None:
                            qr_path = self.config.profile_dir / "whatsapp_qr.png"
                            qr_locator.screenshot(path=str(qr_path))
                            self.logger.info("QR Code capturado em %s — escaneie com o WhatsApp no celular", qr_path)
                    except Exception:
                        self.logger.exception("Falha ao capturar QR Code em headless")

            page.wait_for_timeout(1000)

        # Antes de lançar a exceção, capturamos artefatos para diagnóstico
        # (screenshot e HTML) para entender o que o WhatsApp Web exibiu em
        # headless e facilitar correções.
        try:
            failure_png = self.config.profile_dir / "last_headless_failure.png"
            failure_html = self.config.profile_dir / "last_headless_failure.html"
            try:
                page.screenshot(path=str(failure_png), full_page=True)
            except Exception:
                # fallback: screenshot sem full_page
                try:
                    page.screenshot(path=str(failure_png))
                except Exception:
                    self.logger.exception("Falha ao capturar screenshot da página")

            try:
                with open(failure_html, "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                self.logger.exception("Falha ao gravar HTML da página para diagnóstico")

            self.logger.error(
                "Autenticação falhou — salvo screenshot em %s e HTML em %s",
                failure_png,
                failure_html,
            )
        except Exception:
            self.logger.exception("Erro ao criar artefatos de diagnóstico de autenticação")

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

        self._scroll_conversation_to_bottom(page)
        self._wait_for_outgoing_messages_to_stabilize(page)
        previous_outgoing_count = self._count_outgoing_message_bubbles(page)
        previous_outgoing_keys = self._outgoing_message_keys(page)

        if not self._fill_message_box(page, message_box, self.config.message):
            current_content = self._read_textbox_content(message_box)
            raise MessageSendError(
                "Mensagem não foi inserida corretamente no campo de composição. "
                f"Conteúdo atual: {current_content!r}"
            )

        send_button = self._first_visible_locator(page, self._send_button_selectors, timeout_ms=5000)
        if send_button is not None:
            self.logger.info("Botão Enviar encontrado. Clicando para enviar")
            self._click_send_button(send_button)
        else:
            self.logger.warning("Botão Enviar não encontrado. Tentando enviar com Enter")
            message_box.click()
            page.keyboard.press("Enter")

        page.wait_for_timeout(500)
        self._scroll_conversation_to_bottom(page)

        send_confirmed = self._wait_for_send_confirmation(
            page,
            message_box,
            previous_outgoing_count,
            previous_outgoing_keys,
            timeout_seconds=5,
        )

        if not send_confirmed:
            current_content = self._read_textbox_content(message_box)
            if current_content:
                self.logger.warning(
                    "Envio não confirmado após clique no botão. Tentando enviar novamente com Enter"
                )
                message_box.click()
                page.keyboard.press("Enter")
            else:
                self.logger.info(
                    "Mensagem saiu do campo de composição. Aguardando confirmação do WhatsApp Web"
                )

            send_confirmed = self._wait_for_send_confirmation(
                page,
                message_box,
                previous_outgoing_count,
                previous_outgoing_keys,
                timeout_seconds=self.config.timeout_seconds,
            )

        if not send_confirmed:
            current_content = self._read_textbox_content(message_box)
            outgoing_count = self._count_outgoing_message_bubbles(page)
            latest_status = self._latest_new_outgoing_message_status(
                page,
                previous_outgoing_count,
                previous_outgoing_keys,
            )
            raise MessageSendError(
                "Mensagem não foi confirmada pelo WhatsApp Web. "
                f"Campo atual: {current_content!r}. "
                f"Mensagens de saída antes/depois: {previous_outgoing_count}/{outgoing_count}. "
                f"Status detectado: {latest_status}."
            )

        self.logger.info("Mensagem enviada e confirmada")

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

    def _click_send_button(self, send_button: Locator) -> None:
        try:
            button = send_button.locator("xpath=ancestor-or-self::button[1]")
            if button.is_visible(timeout=500):
                button.click()
                return
        except PlaywrightError:
            pass

        send_button.click()

    def _fill_message_box(self, page: Page, locator: Locator, value: str) -> bool:
        attempts = (
            ("fill", self._fill_message_with_fill),
            ("keyboard.type", self._fill_message_with_keyboard_type),
            ("keyboard.insert_text", self._fill_message_with_insert_text),
            ("document.execCommand", self._fill_message_with_exec_command),
        )

        for attempt_name, attempt in attempts:
            try:
                self._clear_message_box(page, locator)
                attempt(page, locator, value)

                if self._wait_for_textbox_content(
                    page,
                    locator,
                    value,
                    timeout_ms=3000,
                ):
                    self.logger.info(
                        "Mensagem inserida no campo de composição usando %s",
                        attempt_name,
                    )
                    return True

                current_content = self._read_textbox_content(locator)
                self.logger.warning(
                    "Tentativa de inserir mensagem com %s falhou. Conteúdo atual: %r",
                    attempt_name,
                    current_content,
                )
            except PlaywrightError as exc:
                self.logger.warning(
                    "Tentativa de inserir mensagem com %s falhou: %s",
                    attempt_name,
                    exc,
                )

        return False

    def _clear_message_box(self, page: Page, locator: Locator) -> None:
        locator.wait_for(state="visible", timeout=5000)
        locator.scroll_into_view_if_needed(timeout=5000)
        locator.click(timeout=5000)
        locator.focus(timeout=5000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")

        if self._normalize_text(self._read_textbox_content(locator)) != "":
            locator.fill("")

        page.wait_for_timeout(100)

    def _fill_message_with_fill(self, page: Page, locator: Locator, value: str) -> None:
        del page
        locator.fill(value)

    def _fill_message_with_keyboard_type(
        self,
        page: Page,
        locator: Locator,
        value: str,
    ) -> None:
        locator.click(timeout=5000)
        locator.focus(timeout=5000)
        page.keyboard.type(value, delay=10)

    def _fill_message_with_insert_text(
        self,
        page: Page,
        locator: Locator,
        value: str,
    ) -> None:
        locator.click(timeout=5000)
        locator.focus(timeout=5000)
        page.keyboard.insert_text(value)

    def _fill_message_with_exec_command(
        self,
        page: Page,
        locator: Locator,
        value: str,
    ) -> None:
        del page
        locator.evaluate(
            """
            (el, text) => {
                el.focus();

                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(el);
                selection.removeAllRanges();
                selection.addRange(range);

                document.execCommand("insertText", false, text);
                el.dispatchEvent(
                    new InputEvent("input", {
                        bubbles: true,
                        cancelable: true,
                        inputType: "insertText",
                        data: text,
                    })
                );
            }
            """,
            value,
            timeout=5000,
        )

    def _fill_textbox(self, page: Page, locator: Locator, value: str) -> None:
        locator.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        locator.fill(value)

    def _wait_for_textbox_content(
        self,
        page: Page,
        locator: Locator,
        expected_value: str,
        timeout_ms: int,
    ) -> bool:
        expected = self._normalize_text(expected_value)
        deadline = time.monotonic() + (timeout_ms / 1000)

        while time.monotonic() < deadline:
            current = self._normalize_text(self._read_textbox_content(locator))
            if current == expected:
                return True

            page.wait_for_timeout(200)

        return False

    def _wait_for_send_confirmation(
        self,
        page: Page,
        message_box: Locator,
        previous_outgoing_count: int,
        previous_outgoing_keys: set[str],
        timeout_seconds: int,
    ) -> bool:
        deadline = time.monotonic() + timeout_seconds
        last_logged_status: str | None = None
        empty_composer_since: float | None = None

        while time.monotonic() < deadline:
            message_box_empty = self._normalize_text(self._read_textbox_content(message_box)) == ""
            can_accept_empty_composer = False
            latest_message = self._latest_new_outgoing_message_bubble(
                page,
                previous_outgoing_count,
                previous_outgoing_keys,
            )

            if message_box_empty and latest_message is not None:
                if self._has_any_related_element(latest_message, self._failed_status_selectors):
                    raise MessageSendError("WhatsApp Web indicou falha no envio da mensagem")

                if self._has_any_related_element(latest_message, self._sent_status_selectors):
                    return True

                if self._has_any_related_element(latest_message, self._pending_status_selectors):
                    if last_logged_status != "pendente":
                        self.logger.info("Mensagem ainda pendente de envio no WhatsApp Web")
                        last_logged_status = "pendente"
                else:
                    if last_logged_status != "sem_status":
                        self.logger.info(
                            "Nova mensagem de saida encontrada, mas sem status de envio confirmado"
                        )
                        last_logged_status = "sem_status"
                    can_accept_empty_composer = True
            else:
                last_logged_status = None

                if message_box_empty:
                    self._scroll_conversation_to_bottom(page)
                    can_accept_empty_composer = True

            if can_accept_empty_composer:
                if self._has_visible_message_failure(page):
                    raise MessageSendError("WhatsApp Web indicou falha no envio da mensagem")

                if self._has_visible_message_pending(page):
                    empty_composer_since = None
                else:
                    if empty_composer_since is None:
                        empty_composer_since = time.monotonic()

                    if time.monotonic() - empty_composer_since >= 2:
                        self.logger.info(
                            "Mensagem aceita pelo WhatsApp Web: campo de composicao vazio "
                            "e nenhum erro ou pendencia visivel"
                        )
                        return True
            else:
                empty_composer_since = None

            page.wait_for_timeout(300)

        return False

    def _read_textbox_content(self, locator: Locator) -> str:
        try:
            content = locator.evaluate(
                """
                el => {
                    const raw = (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)
                        ? el.value
                        : (el.innerText || el.textContent || "");
                    return raw.replace(/\u200B/g, "").replace(/\u00A0/g, " ").trim();
                }
                """,
                timeout=500,
            )
        except PlaywrightError:
            return ""

        return content if isinstance(content, str) else ""

    def _count_outgoing_message_bubbles(self, page: Page, message: str | None = None) -> int:
        return len(self._outgoing_message_bubbles(page, message))

    def _latest_new_outgoing_message_bubble(
        self,
        page: Page,
        previous_outgoing_count: int,
        previous_outgoing_keys: set[str],
    ) -> Locator | None:
        matches = self._outgoing_message_bubbles(page)
        if not matches:
            return None

        keyed_matches: list[Locator] = []
        for match in matches:
            key = self._outgoing_message_key(match)
            if key is not None and key not in previous_outgoing_keys:
                keyed_matches.append(match)

        if keyed_matches:
            return keyed_matches[-1]

        if len(matches) > previous_outgoing_count:
            return matches[-1]

        return None

    def _latest_new_outgoing_message_status(
        self,
        page: Page,
        previous_outgoing_count: int,
        previous_outgoing_keys: set[str],
    ) -> str:
        latest_message = self._latest_new_outgoing_message_bubble(
            page,
            previous_outgoing_count,
            previous_outgoing_keys,
        )
        if latest_message is None:
            return "nova mensagem de saída não encontrada"

        if self._has_any_related_element(latest_message, self._failed_status_selectors):
            return "falha"
        if self._has_any_related_element(latest_message, self._pending_status_selectors):
            return "pendente"
        if self._has_any_related_element(latest_message, self._sent_status_selectors):
            return "enviada"

        return "sem status de envio confirmado"

    def _outgoing_message_bubbles(self, page: Page, message: str | None = None) -> list[Locator]:
        message_text = self._normalize_text(message) if message is not None else None
        if message is not None and not message_text:
            return []

        for selector in self._outgoing_message_selectors:
            try:
                selector_matches: list[Locator] = []
                containers = page.locator(selector)
                total = containers.count()
                if total == 0:
                    continue

                for index in range(total):
                    container = containers.nth(index)
                    normalized_content = self._normalize_text(
                        container.inner_text(timeout=500)
                    )
                    if message_text is None or message_text in normalized_content:
                        selector_matches.append(container)

                if selector_matches:
                    return selector_matches
            except PlaywrightError:
                continue

        return []

    def _outgoing_message_keys(self, page: Page, message: str | None = None) -> set[str]:
        keys: set[str] = set()

        for bubble in self._outgoing_message_bubbles(page, message):
            key = self._outgoing_message_key(bubble)
            if key is not None:
                keys.add(key)

        return keys

    def _outgoing_message_key(self, locator: Locator) -> str | None:
        try:
            key = locator.evaluate(
                """
                el => {
                    let current = el;

                    for (let depth = 0; current && depth < 10; depth += 1) {
                        const dataId = current.getAttribute("data-id");
                        if (dataId) {
                            return `data-id:${dataId}`;
                        }

                        const prePlainText = current.getAttribute("data-pre-plain-text");
                        if (prePlainText) {
                            return `data-pre-plain-text:${prePlainText}`;
                        }

                        const id = current.getAttribute("id");
                        if (id) {
                            return `id:${id}`;
                        }

                        current = current.parentElement;
                    }

                    return null;
                }
                """,
                timeout=500,
            )
        except PlaywrightError:
            return None

        return key if isinstance(key, str) and key else None

    def _scroll_conversation_to_bottom(self, page: Page) -> None:
        for selector in self._conversation_messages_selectors:
            container = page.locator(selector).first
            try:
                if not container.is_visible(timeout=100):
                    continue

                container.evaluate(
                    """
                    el => {
                        const nodes = [el, ...el.querySelectorAll("*")];
                        for (const node of nodes) {
                            if (node.scrollHeight > node.clientHeight) {
                                node.scrollTop = node.scrollHeight;
                            }
                        }
                    }
                    """,
                    timeout=500,
                )
                return
            except PlaywrightError:
                continue

    def _has_visible_message_failure(self, page: Page) -> bool:
        return self._has_visible_conversation_status(page, self._failed_status_selectors)

    def _has_visible_message_pending(self, page: Page) -> bool:
        return self._has_visible_conversation_status(page, self._pending_status_selectors)

    def _has_visible_conversation_status(self, page: Page, selectors: tuple[str, ...]) -> bool:
        for bubble in self._outgoing_message_bubbles(page):
            if self._has_any_related_element(bubble, selectors):
                return True

        for container_selector in self._conversation_messages_selectors:
            container = page.locator(container_selector).first
            try:
                if container.is_visible(timeout=100) and self._has_any_descendant(
                    container,
                    selectors,
                ):
                    return True
            except PlaywrightError:
                continue

        return False

    def _wait_for_outgoing_messages_to_stabilize(self, page: Page) -> None:
        deadline = time.monotonic() + min(self.config.timeout_seconds, 5)
        stable_since: float | None = None
        previous_count: int | None = None

        while time.monotonic() < deadline:
            current_count = self._count_outgoing_message_bubbles(page)
            if current_count == previous_count:
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= 1:
                    return
            else:
                previous_count = current_count
                stable_since = None

            page.wait_for_timeout(250)

    def _has_any_related_element(self, locator: Locator, selectors: tuple[str, ...]) -> bool:
        roots = (
            locator,
            locator.locator('xpath=ancestor-or-self::*[@role="row"][1]'),
            locator.locator('xpath=ancestor-or-self::*[@data-id][1]'),
            locator.locator('xpath=ancestor-or-self::*[@data-testid="msg-container"][1]'),
            locator.locator(
                'xpath=ancestor-or-self::div[contains(concat(" ", normalize-space(@class), " "), " message-out ")][1]'
            ),
        )

        for root in roots:
            if self._has_any_descendant(root, selectors):
                return True

        return False

    def _has_any_descendant(self, locator: Locator, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            try:
                if locator.locator(selector).count() > 0:
                    return True
            except PlaywrightError:
                continue

        return False

    @staticmethod
    def _normalize_text(value: str) -> str:
        cleaned = value.replace("\u200B", "").replace("\u00A0", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

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

    def _capture_page_metadata(self, page: Page) -> None:
        """Grava metadados úteis da página para diagnóstico.

        Gera um arquivo `page_debug.txt` dentro do `profile_dir` com:
        - url atual
        - title
        - navigator.userAgent
        - navigator.webdriver
        - número de cookies
        """
        try:
            info = page.evaluate(
                """
                () => {
                    return {
                        url: window.location.href,
                        title: document.title,
                        userAgent: navigator.userAgent,
                        webdriver: navigator.webdriver === undefined ? 'undefined' : navigator.webdriver,
                        language: navigator.language || null,
                    };
                }
                """
            )
        except Exception:
            info = {
                "url": "<failed to eval>",
                "title": "<failed to eval>",
                "userAgent": "<failed to eval>",
                "webdriver": "<failed to eval>",
                "language": "<failed to eval>",
            }

        try:
            cookies = page.context.cookies()
            cookies_count = len(cookies)
        except Exception:
            cookies_count = -1

        debug_path = self.config.profile_dir / "page_debug.txt"
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(f"url: {info.get('url')}\n")
                f.write(f"title: {info.get('title')}\n")
                f.write(f"userAgent: {info.get('userAgent')}\n")
                f.write(f"webdriver: {info.get('webdriver')}\n")
                f.write(f"language: {info.get('language')}\n")
                f.write(f"cookies_count: {cookies_count}\n")
            self.logger.info("Metadados da página gravados em %s", debug_path)
        except Exception:
            self.logger.exception("Falha ao gravar metadados da página")

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
