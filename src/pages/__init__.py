"""Page Object Model para WhatsApp Web.

Encapsula as interacoes com a UI do WhatsApp Web em Page Objects pequenos:
login/autenticacao, barra lateral/lista de conversas e conversa aberta.
A automacao deve consumir estes objetos para manter seletores fora das camadas
de aplicacao e dominio.
"""

from pages.i_base_page import IBasePage
from pages.pages import ConversationPage, LoginPage, SidebarPage

__all__ = ["IBasePage", "LoginPage", "SidebarPage", "ConversationPage"]
