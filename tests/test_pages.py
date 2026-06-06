import pytest
import logging

from app.pages import LoginPage, SidebarPage, ConversationPage


class FakeLocator:
    def __init__(self, visible=True, inner_text_value="", screenshot_bytes=b"PNG"):
        self._visible = visible
        self._inner_text_value = inner_text_value
        self._screenshot = screenshot_bytes
        # provide .first attribute to mimic Playwright Locator.first
        self.first = self

    def is_visible(self, timeout=0):
        return self._visible

    def screenshot(self, **kwargs):
        return self._screenshot

    def fill(self, value):
        self._inner_text_value = value

    def click(self):
        return None

    def focus(self):
        return None

    def inner_text(self, timeout=0):
        return self._inner_text_value

    def evaluate(self, fn=None, timeout=0):
        # simple evaluator for message box reading
        return self._inner_text_value

    def locator(self, selector):
        # return self for ancestor-or-self lookups
        return self


class FakeLocatorCollection:
    def __init__(self, locators):
        self._locators = locators

    def count(self):
        return len(self._locators)

    def nth(self, index):
        return self._locators[index]

    @property
    def first(self):
        return self._locators[0]


class FakePage:
    def __init__(self, mapping):
        # mapping selector -> FakeLocator or FakeLocatorCollection
        self.mapping = mapping
        self.keyboard = SimpleNamespace(press=lambda k: None, type=lambda s, delay=0: None, insert_text=lambda s: None)
        self.context = SimpleNamespace(cookies=lambda: [])

    def locator(self, selector):
        v = self.mapping.get(selector)
        if v is None:
            # return an invisible locator
            return FakeLocator(visible=False)
        return v

    def wait_for_timeout(self, ms):
        return None

    def goto(self, url, wait_until=None, timeout=None):
        return None


from types import SimpleNamespace


def test_loginpage_detection_and_qr_capture():
    logger = logging.getLogger("test")
    # Page where authenticated selector is visible
    page = FakePage({
        LoginPage._authenticated_selectors[0]: FakeLocator(visible=True),
    })
    login = LoginPage(page, logger)
    assert login.is_authenticated()

    # Page where QR is visible
    page2 = FakePage({
        LoginPage._qr_code_selectors[0]: FakeLocator(visible=True, screenshot_bytes=b"QRPNG"),
    })
    login2 = LoginPage(page2, logger)
    assert login2.has_qr_code()
    qr = login2.capture_qr_code()
    assert qr == b"QRPNG"


def test_sidebar_search_and_find_contact():
    logger = logging.getLogger("test")
    # create a locator that matches contact
    fake_contact = FakeLocator(visible=True, inner_text_value="Grupo Teste")
    page = FakePage({
        SidebarPage._search_box_selectors[0]: FakeLocator(visible=True),
        'span[title]': FakeLocator(visible=True),
    })
    sidebar = SidebarPage(page, logger)
    # search box should exist
    search_box = sidebar.find_search_box()
    assert search_box is not None


def test_conversation_fill_and_send():
    logger = logging.getLogger("test")
    message_locator = FakeLocator(visible=True, inner_text_value="")
    send_locator = FakeLocator(visible=True)
    page = FakePage({
        ConversationPage._message_box_selectors[0]: message_locator,
        ConversationPage._send_button_selectors[0]: send_locator,
    })
    conv = ConversationPage(page, logger)
    assert conv.is_message_box_available()
    ok = conv.fill_message("hello")
    assert ok
    # test send_message doesn't raise
    conv.send_message()



