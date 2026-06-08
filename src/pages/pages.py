import re

from playwright.sync_api import Error as PlaywrightError, Locator

from pages.i_base_page import IBasePage


DEFAULT_SHORT_TIMEOUT_MS = 300
DEFAULT_LOCATOR_TIMEOUT_MS = 5000
CONTACT_SEARCH_POLL_MS = 500


class LoginPage(IBasePage):
    """Page Object da tela de login e autenticacao do WhatsApp Web."""

    _authenticated_selectors = (
        '[data-testid="chat-list-search-container"] input[role="textbox"]',
        'input[role="textbox"][data-tab="3"]',
        'input[role="textbox"][aria-label*="Pesquisar" i]',
        'input[role="textbox"][aria-label*="Search" i]',
        '#pane-side [data-testid="chat-list"]',
        '#pane-side div[role="grid"][aria-label*="Lista de conversas" i]',
        '#pane-side div[role="grid"][aria-label*="Chat list" i]',
        'div[data-testid="chat-list"]',
        'div[aria-label*="Lista de conversas" i]',
        'div[aria-label*="Chat list" i]',
    )

    _qr_code_selectors = (
        'canvas[aria-label*="Scan" i]',
        'canvas[aria-label*="Escanear" i]',
        '[data-testid="qrcode"]',
        "canvas",
    )

    def is_authenticated(self, timeout_ms: int = DEFAULT_SHORT_TIMEOUT_MS) -> bool:
        """Retorna True quando a lista de conversas esta disponivel."""
        return self._is_any_selector_visible(self._authenticated_selectors, timeout_ms)

    def has_qr_code(self, timeout_ms: int = DEFAULT_SHORT_TIMEOUT_MS) -> bool:
        """Retorna True quando o QR Code de autenticacao esta visivel."""
        return self._is_any_selector_visible(self._qr_code_selectors, timeout_ms)

    def capture_qr_code(self) -> bytes | None:
        """Captura o QR Code visivel como PNG."""
        qr_locator = self._first_visible_locator(self._qr_code_selectors, timeout_ms=500)
        if qr_locator is None:
            return None

        try:
            return qr_locator.screenshot()
        except PlaywrightError:
            return None


class SidebarPage(IBasePage):
    """Page Object da barra lateral e lista de conversas."""

    _search_box_selectors = (
        '[data-testid="chat-list-search-container"] input[role="textbox"]',
        'input[role="textbox"][aria-label*="Pesquisar ou comecar" i]',
        'input[role="textbox"][aria-label*="Search or start" i]',
        'input[role="textbox"][aria-label*="Pesquisar" i]',
        'input[role="textbox"][aria-label*="Search" i]',
        'input[role="textbox"][aria-label*="Buscar" i]',
        'input[role="textbox"][placeholder*="Pesquisar" i]',
        'input[role="textbox"][placeholder*="Search" i]',
        'input[role="textbox"][placeholder*="Buscar" i]',
        '#pane-side div[role="textbox"][contenteditable="true"]',
        '#side div[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"][data-tab="3"]',
    )

    def find_search_box(self) -> Locator | None:
        """Retorna a caixa de busca de contatos, se ela estiver visivel."""
        return self._first_visible_locator(
            self._search_box_selectors,
            timeout_ms=DEFAULT_LOCATOR_TIMEOUT_MS,
        )

    def search_contact(self, contact_name: str) -> None:
        """Limpa a busca atual e pesquisa pelo contato ou grupo informado."""
        search_box = self.find_search_box()
        if search_box is None:
            raise RuntimeError("Campo de busca nao encontrado")

        self._fill_text_field(search_box, contact_name)

    def find_contact_result(self, target_name: str, timeout_seconds: int = 60) -> Locator | None:
        """Retorna o primeiro resultado que corresponde exatamente ao contato ou grupo."""
        escaped_target = re.escape(target_name)
        exact_text = re.compile(rf"^\s*{escaped_target}\s*$", re.IGNORECASE)

        candidates = (
            self.page.locator('#pane-side [data-testid="cell-frame-title"] span[title]')
            .filter(has_text=exact_text)
            .first,
            self.page.locator('[data-testid="cell-frame-title"] span[title]')
            .filter(has_text=exact_text)
            .first,
            self.page.locator('div[role="grid"] span[title]').filter(has_text=exact_text).first,
            self.page.locator('span[title]').filter(has_text=exact_text).first,
        )

        timeout_ms = timeout_seconds * 1000
        elapsed_ms = 0
        while elapsed_ms < timeout_ms:
            for candidate in candidates:
                try:
                    if candidate.is_visible(timeout=DEFAULT_SHORT_TIMEOUT_MS):
                        return candidate
                except PlaywrightError:
                    continue

            self.page.wait_for_timeout(CONTACT_SEARCH_POLL_MS)
            elapsed_ms += CONTACT_SEARCH_POLL_MS

        return None

    def click_contact(self, locator: Locator) -> None:
        """Abre o contato ou grupo representado pelo resultado encontrado."""
        self._click_locator_or_ancestor(
            locator,
            'xpath=ancestor::*[@role="listitem" or @role="gridcell"][1]',
        )

    def _fill_text_field(self, locator: Locator, value: str) -> None:
        locator.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        locator.fill(value)

    @staticmethod
    def _click_locator_or_ancestor(locator: Locator, ancestor_selector: str) -> None:
        try:
            ancestor = locator.locator(ancestor_selector)
            if ancestor.is_visible(timeout=500):
                ancestor.click()
                return
        except PlaywrightError:
            pass

        locator.click()


class ConversationPage(IBasePage):
    """Page Object da conversa aberta no WhatsApp Web."""

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

    def find_message_box(self) -> Locator | None:
        """Retorna o campo de composicao de mensagens, se ele estiver visivel."""
        return self._first_visible_locator(
            self._message_box_selectors,
            timeout_ms=DEFAULT_LOCATOR_TIMEOUT_MS,
        )

    def is_message_box_available(self) -> bool:
        """Retorna True quando a conversa aceita digitacao de mensagem."""
        return self.find_message_box() is not None

    def fill_message(self, message: str) -> bool:
        """Preenche o campo de mensagem e valida o conteudo inserido."""
        message_box = self.find_message_box()
        if message_box is None:
            return False

        message_box.click()
        message_box.focus()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        message_box.fill(message)

        self.page.wait_for_timeout(200)
        content = self._read_message_box_content(message_box)
        return self._normalize_text(content) == self._normalize_text(message)

    def send_message(self) -> None:
        """Envia a mensagem clicando no botao de envio ou usando Enter como fallback."""
        send_button = self._first_visible_locator(
            self._send_button_selectors,
            timeout_ms=DEFAULT_LOCATOR_TIMEOUT_MS,
        )

        if send_button is not None:
            SidebarPage._click_locator_or_ancestor(
                send_button,
                "xpath=ancestor-or-self::button[1]",
            )
            return

        message_box = self.find_message_box()
        if message_box is not None:
            message_box.click()
            self.page.keyboard.press("Enter")

    def _read_message_box_content(self, locator: Locator) -> str:
        """Le o conteudo atual do campo de mensagem."""
        try:
            content = locator.evaluate(
                """
                el => {
                    const raw = (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)
                        ? el.value
                        : (el.innerText || el.textContent || "");
                    return raw.replace(/\u200B/g, "").replace(/\u00A0/g, " ").trim();
                }
                """
            )
        except PlaywrightError:
            return ""

        return content if isinstance(content, str) else ""
