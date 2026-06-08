"""Page Object Model para WhatsApp Web.

Encapsula a interação com elementos da UI do WhatsApp Web,
separando a automação das páginas específicas (login, conversa, etc)
da lógica de negócio.
"""

from pages.i_base_page import IBasePage
from pages.pages import LoginPage, SidebarPage, ConversationPage

__all__ = ['IBasePage', 'LoginPage', 'SidebarPage', 'ConversationPage']

