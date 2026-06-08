# Arquitetura do WhatsApp Notify

## Visao Geral

A aplicacao segue Clean Architecture com separacao clara entre API, aplicacao, dominio e infraestrutura. O envio usa FastAPI na borda HTTP, servicos para orquestracao, modelos/excecoes de dominio e adaptadores concretos para Playwright/WhatsApp Web.

## Camadas

```text
Presentation  -> src/api/, src/main.py
Application   -> src/services/
Domain        -> src/domain/
Infrastructure-> src/repositories/, src/pages/, src/whatsapp_service.py
```

## Estrutura Atual

```text
src/
|-- api/                         # Rotas, handlers, schemas e OpenAPI
|-- config.py                    # Configuracao via ambiente
|-- domain/                      # Modelos e excecoes de dominio
|-- logger.py                    # Configuracao de logging
|-- main.py                      # Entry point da aplicacao
|-- pages/                       # Page Object Model do WhatsApp Web
|   |-- i_base_page.py           # IBasePage e helpers compartilhados
|   |-- pages.py                 # LoginPage, SidebarPage, ConversationPage
|   `-- __init__.py              # Exports publicos
|-- repositories/                # Interfaces e adaptadores concretos
|-- services/                    # Orquestracao de negocio
`-- whatsapp_service.py          # Automacao Playwright base
```

## Responsabilidades

- `domain/`: contem regras puras, modelos e excecoes sem dependencia de FastAPI ou Playwright.
- `services/`: valida e orquestra casos de uso usando interfaces de repositorio.
- `repositories/`: adapta integracoes externas para as interfaces esperadas pela aplicacao.
- `pages/`: centraliza seletores e acoes de UI do WhatsApp Web em Page Objects.
- `api/`: traduz HTTP para chamadas de aplicacao e mapeia erros para respostas.
- `whatsapp_service.py`: mantem a automacao Playwright existente e compatibilidade operacional.

## Padroes

### Clean Architecture

As dependencias apontam para dentro: API e infraestrutura dependem da aplicacao/dominio, mas dominio nao conhece frameworks ou Playwright.

### Repository Pattern

`INotificationRepository` define a operacao de envio. `PlaywrightNotificationRepository` implementa essa porta usando WhatsApp Web e converte erros da automacao para erros de dominio.

### Service Layer

`NotificationService` concentra o fluxo de negocio: cria/valida `Notification`, registra eventos relevantes e delega o envio ao repositorio.

### Dependency Injection

Repositorios e logger sao injetados nos servicos. Isso permite testar a regra de negocio com mocks e trocar a implementacao de envio sem alterar a camada de aplicacao.

### Page Object Model

`pages/pages.py` contem Page Objects pequenos e focados:

```python
class LoginPage(IBasePage):
    def is_authenticated(self) -> bool: ...
    def has_qr_code(self) -> bool: ...
    def capture_qr_code(self) -> bytes | None: ...

class SidebarPage(IBasePage):
    def search_contact(self, contact_name: str) -> None: ...
    def find_contact_result(self, target_name: str) -> Locator | None: ...
    def click_contact(self, locator: Locator) -> None: ...

class ConversationPage(IBasePage):
    def find_message_box(self) -> Locator | None: ...
    def fill_message(self, message: str) -> bool: ...
    def send_message(self) -> None: ...
```

Seletores devem ficar nos Page Objects ou na automacao Playwright, nunca nas camadas de dominio ou servico.

## Fluxo de Execucao

1. Cliente chama `POST /notifications`.
2. A API valida payload e carrega configuracao.
3. A factory cria `PlaywrightNotificationRepository`.
4. `NotificationService` valida o dominio e chama `repository.send()`.
5. `PlaywrightNotificationRepository` instancia `WhatsAppService`.
6. `WhatsAppService` executa a automacao no WhatsApp Web.
7. Erros de automacao sao convertidos para erros de dominio/API.
8. A API retorna sucesso ou erro estruturado.

## Mapeamento de Erros

| Erro de dominio | HTTP | Codigo |
| --- | --- | --- |
| `AuthenticationError` | 500 | `AUTENTICACAO_EXPIRADA` |
| `TargetNotFoundError` | 400 | `DESTINO_NAO_ENCONTRADO` |
| `SendError` | 500 | `FALHA_NO_ENVIO` |
| `DomainError` | 500 | `FALHA_NA_AUTOMACAO` |
| erro inesperado | 500 | `ERRO_INTERNO` |

## Como Estender

### Novo repositorio

1. Crie um arquivo em `src/repositories/`.
2. Implemente `INotificationRepository`.
3. Ajuste a factory da API para selecionar a implementacao.
4. Teste usando mocks da interface.

### Nova pagina POM

1. Adicione a classe em `src/pages/pages.py` estendendo `IBasePage`.
2. Declare seletores como atributos privados da classe.
3. Exponha metodos com acoes de alto nivel, sem vazar seletores.
4. Exporte a classe em `src/pages/__init__.py`.
5. Use a classe na automacao quando necessario.

## Regras de Manutencao

- Nao coloque regra de negocio em Page Objects.
- Nao coloque seletor de Playwright em `domain/` ou `services/`.
- Prefira mensagens de erro de dominio nas camadas internas e mapeamento HTTP apenas em `api/`.
- Mantenha seletores alternativos quando o WhatsApp Web variar entre idiomas ou versoes.
