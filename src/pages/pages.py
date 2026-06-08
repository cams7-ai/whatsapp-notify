import re
import time
from playwright.sync_api import Error as PlaywrightError, Locator
from pages.i_base_page import IBasePage

class LoginPage(IBasePage):
    """POM para a tela de login/autenticação do WhatsApp Web."""

    _authenticated_selectors = (
        '[data-testid="chat-list-search-container"] input[role="textbox"]',
        'input[role="textbox"][data-tab="3"]',
        'input[role="textbox"][aria-label*="Pesquisar" i]',
        'input[role="textbox"][aria-label*="Search" i]',
        '#pane-side [data-testid="chat-list"]',
        '#pane-side div[role="grid"][aria-label*="Lista de conversas" i]',
        '#pane-side div[role="grid"][aria-label*="Chat list" i]',
    )

    _qr_code_selectors = (
        'canvas[aria-label*="Scan" i]',
        'canvas[aria-label*="Escanear" i]',
        '[data-testid="qrcode"]',
        "canvas",
    )

    def is_authenticated(self, timeout_ms: int = 300) -> bool:
        """Verifica se o usuário está autenticado."""
        return self._is_any_selector_visible(self._authenticated_selectors, timeout_ms)

    def has_qr_code(self, timeout_ms: int = 300) -> bool:
        """Verifica se há QR Code sendo exibido."""
        return self._is_any_selector_visible(self._qr_code_selectors, timeout_ms)

    def capture_qr_code(self) -> bytes | None:
        """Captura o QR Code em bytes (PNG)."""
        qr_locator = self._first_visible_locator(self._qr_code_selectors, timeout_ms=500)
        if qr_locator is None:
            return None

        try:
            return qr_locator.screenshot()
        except PlaywrightError:
            return None

class SidebarPage(IBasePage):
    """POM para a barra lateral (lista de conversas) do WhatsApp Web."""

    _search_box_selectors = (
        '[data-testid="chat-list-search-container"] input[role="textbox"]',
        'input[role="textbox"][aria-label*="Pesquisar ou começar" i]',
        'input[role="textbox"][aria-label*="Search or start" i]',
        'input[role="textbox"][aria-label*="Pesquisar" i]',
        'input[role="textbox"][aria-label*="Search" i]',
        'input[role="textbox"][aria-label*="Buscar" i]',
    )

    def find_search_box(self) -> Locator | None:
        """Encontra a caixa de busca de contatos."""
        return self._first_visible_locator(self._search_box_selectors, timeout_ms=5000)

    def search_contact(self, contact_name: str) -> None:
        """Digita o nome do contato na caixa de busca."""
        search_box = self.find_search_box()
        if search_box is None:
            raise RuntimeError("Campo de busca não encontrado")

        search_box.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        search_box.fill(contact_name)

    def find_contact_result(self, target_name: str, timeout_seconds: int = 60) -> Locator | None:
        """Encontra o resultado de busca do contato/grupo."""
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

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for candidate in candidates:
                try:
                    if candidate.is_visible(timeout=300):
                        return candidate
                except PlaywrightError:
                    continue

            self.page.wait_for_timeout(500)

        return None

    def click_contact(self, locator: Locator) -> None:
        """Clica em um contato/grupo encontrado."""
        try:
            row = locator.locator('xpath=ancestor::*[@role="listitem" or @role="gridcell"][1]')
            if row.is_visible(timeout=500):
                row.click()
                return
        except PlaywrightError:
            pass

        locator.click()

class ConversationPage(IBasePage):
    """POM para a página/conversa aberta do WhatsApp Web."""

    _message_box_selectors = (
        'footer [data-testid="conversation-compose-box-input"][contenteditable="true"]',
        'div[data-testid="conversation-compose-box-input"][contenteditable="true"]',
        'footer div[role="textbox"][contenteditable="true"][aria-placeholder*="Digite uma mensagem" i]',
        'footer div[role="textbox"][contenteditable="true"]',
    )

    _send_button_selectors = (
        'footer button[aria-label*="Send" i][aria-disabled="false"]',
        'footer button[aria-label*="Enviar" i][aria-disabled="false"]',
        'button[data-tab="11"][aria-label*="Enviar" i][aria-disabled="false"]',
    )

    def find_message_box(self) -> Locator | None:
        """Encontra o campo de composição de mensagens."""
        return self._first_visible_locator(self._message_box_selectors, timeout_ms=5000)

    def is_message_box_available(self) -> bool:
        """Verifica se o campo de mensagem está disponível."""
        return self.find_message_box() is not None

    def fill_message(self, message: str) -> bool:
        """Preenche o campo de mensagem com o texto."""
        message_box = self.find_message_box()
        if message_box is None:
            return False

        message_box.click()
        message_box.focus()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        message_box.fill(message)

        # Verifiação
        time.sleep(0.2)
        content = self._read_message_box_content(message_box)
        return self._normalize_text(content) == self._normalize_text(message)

    def send_message(self) -> None:
        """Envia a mensagem clicando no botão ou pressionando Enter."""
        send_button = self._first_visible_locator(self._send_button_selectors, timeout_ms=5000)

        if send_button is not None:
            try:
                button = send_button.locator("xpath=ancestor-or-self::button[1]")
                if button.is_visible(timeout=500):
                    button.click()
                    return
            except PlaywrightError:
                pass
            send_button.click()
        else:
            message_box = self.find_message_box()
            if message_box:
                message_box.click()
                self.page.keyboard.press("Enter")

    def _read_message_box_content(self, locator: Locator) -> str:
        """Lê o conteúdo atual do campo de mensagem."""
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
