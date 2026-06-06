# Arquitetura do WhatsApp Notify

## Visão Geral

A aplicação segue **Clean Architecture** com separação clara de camadas, aplicando **SOLID**, **Repository Pattern**, **Service Layer**, **Dependency Injection** e **Page Object Model (POM)**.

```
┌─────────────────────────────────────────────────────────┐
│ Presentation Layer (FastAPI)                            │
│ main.py - Endpoints HTTP, modelo de requisição/resposta │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ Application Layer (Service)                             │
│ services/__init__.py - Orquestração de negócio          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ Domain Layer                                            │
│ domain/__init__.py - Modelos e exceções de domínio      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ Infrastructure Layer (Repository & Pages)              │
│ repositories/__init__.py - Adaptadores concretos        │
│ pages/__init__.py - Interações com Playwright/UI        │
│ whatsapp_service.py - Automação base (manter compatível)│
└─────────────────────────────────────────────────────────┘
```

## Estrutura de Diretórios

```
src/app/
├── __init__.py
├── config.py                  # Carregamento de variáveis
├── logger.py                  # Configuração de logging
├── main.py                    # Endpoints FastAPI (Presentation)
├── whatsapp_service.py        # Automação base Playwright (mantém compatibilidade)
│
├── domain/                    # Domain Layer
│   └── __init__.py            # Modelos (Notification) e exceções de domínio
│
├── repositories/              # Repository Pattern
│   └── __init__.py            # Interfaces (ABC) e implementações
│
├── services/                  # Service Layer
│   └── __init__.py            # Orquestração de negócio
│
└── pages/                     # Page Object Model
    └── __init__.py            # BasePage, LoginPage, SidebarPage, ConversationPage
```

## Padrões Implementados

### 1. Clean Architecture

A arquitetura separa as preocupações em camadas independentes:

- **Domain**: Lógica pura de negócio, independente de frameworks
- **Application**: Orquestração (Service Layer)
- **Infrastructure**: Detalhes de implementação (Playwright, HTTP, persistência)
- **Presentation**: Interfaces com o mundo exterior (FastAPI)

Benefício: Mudanças em frameworks (ex: trocar FastAPI por Django) não afetam lógica de domínio.

### 2. SOLID

- **S (Single Responsibility)**: Cada classe tem uma única responsabilidade
  - `NotificationService`: orquestra envio
  - `PlaywrightNotificationRepository`: implementa envio via Playwright
  - `LoginPage`, `SidebarPage`, `ConversationPage`: gerenciam interações específicas com UI

- **O (Open/Closed)**: Classes abertas para extensão, fechadas para modificação
  - Novos repositórios (ex: `TwilioRepository`) podem ser criados sem alterar `NotificationService`

- **L (Liskov Substitution)**: Implementações de interfaces são intercambiáveis
  - `PlaywrightNotificationRepository` implementa `NotificationRepository`
  - Qualquer nova implementação pode substituir sem quebrar o serviço

- **I (Interface Segregation)**: Clientes dependem de interfaces mínimas
  - `NotificationRepository` oferece apenas `send(target_name, message)`

- **D (Dependency Inversion)**: Código de alto nível depende de abstrações
  - `NotificationService` depende de `NotificationRepository`, não de `PlaywrightNotificationRepository`

### 3. Repository Pattern

Encapsula o acesso a dados/integrações atrás de uma interface.

```python
# Interface abstrata
class NotificationRepository(ABC):
    @abstractmethod
    def send(self, target_name: str, message: str) -> None:
        raise NotImplementedError

# Implementação concreta (adaptador Playwright)
class PlaywrightNotificationRepository(NotificationRepository):
    def send(self, target_name: str, message: str) -> None:
        # Lógica Playwright aqui
```

Benefício: Trocar Playwright por outra biblioteca requer apenas nova implementação de `NotificationRepository`.

### 4. Service Layer

Concentra lógica de negócio sem conhecer detalhes de implementação.

```python
class NotificationService:
    def __init__(self, repository: NotificationRepository, logger):
        self.repository = repository
    
    def send(self, target_name: str, message: str) -> None:
        # Valida domínio (Notification)
        notification = Notification(target_name, message)
        # Delega ao repositório
        self.repository.send(notification.target_name, notification.message)
```

Benefício: Lógica de validação, logging e tratamento de erros centralizados.

### 5. Dependency Injection (DI)

Dependências são injetadas em vez de criadas internamente.

```python
# Em main.py (Presentation)
def _send_message(config: AppConfig) -> None:
    # Cria repositório
    repository = PlaywrightNotificationRepository(config, logger)
    # Injeta repositório no serviço
    service = NotificationService(repository, logger)
    # Usa o serviço
    service.send(config.target_name, config.message)
```

Benefício: Fácil de testar (mockar `NotificationRepository`), fácil trocar implementações.

### 6. Page Object Model (POM)

Encapsula seletores e ações de cada "página" do WhatsApp Web.

```python
class LoginPage(BasePage):
    _authenticated_selectors = (...)
    _qr_code_selectors = (...)
    
    def is_authenticated(self) -> bool: ...
    def has_qr_code(self) -> bool: ...
    def capture_qr_code(self) -> bytes | None: ...

class SidebarPage(BasePage):
    def search_contact(self, name: str) -> None: ...
    def find_contact_result(self, name: str) -> Locator | None: ...

class ConversationPage(BasePage):
    def fill_message(self, text: str) -> bool: ...
    def send_message(self) -> None: ...
```

Benefício: Seletores centralizados por página; fácil manutenção quando WhatsApp alterar UI.

## Fluxo de Execução

1. **Cliente HTTP** faz POST para `/notifications`
2. **FastAPI** (main.py) valida corpus, carrega config
3. **main.py** cria `PlaywrightNotificationRepository` → injeta em `NotificationService`
4. **NotificationService**  valida domínio (cria `Notification`)  → chama `repository.send()`
5. **PlaywrightNotificationRepository.send()** instancia `WhatsAppService`
6. **WhatsAppService** usa POMs (`LoginPage`, `SidebarPage`, `ConversationPage`) para interagir com UI
7. Exceções mapeadas: `AuthenticationError` → `AUTENTICACAO_EXPIRADA`, etc.
8. Resposta retorna ao cliente

## Mapeamento de Exceções

| Domain | HTTP | Code |
|--------|------|------|
| `AuthenticationError` | 500 | `AUTENTICACAO_EXPIRADA` |
| `TargetNotFoundError` | 400 | `DESTINO_NAO_ENCONTRADO` |
| `SendError` | 500 | `FALHA_NO_ENVIO` |
| `DomainError` (genérica) | 500 | `FALHA_NA_AUTOMACAO` |
| Outra exceção | 500 | `ERRO_INTERNO` |

## Como Estender

### Adicionar novo repositório (ex: Twilio)

1. Crie `repositories/twilio_repository.py`
2. Implemente `NotificationRepository`
3. Em `main.py`, crie uma factory ou use variável de ambiente para escolher qual repository usar

### Adicionar nova página (ex: StatusPage)

1. Crie classe que estenda `BasePage` em `pages/__init__.py`
2. Defina seletores específicos
3. Implemente métodos de interação
4. Use em `WhatsAppService`

### Teste unitário

```python
from unittest.mock import Mock
from app.services import NotificationService
from app.domain import TargetNotFoundError

def test_send_notifies_when_target_not_found():
    repo = Mock()
    repo.send.side_effect = TargetNotFoundError("Not found")
    service = NotificationService(repo, logger)
    
    with pytest.raises(TargetNotFoundError):
        service.send("Unknown", "Test")
    
    repo.send.assert_called_once_with("Unknown", "Test")
```

## Próximas Melhorias

1. **Dependency Injector**: Usar `dependency-injector` para gerenciar DI automaticamente
2. **Camada de Testes**: Testes unitários e de integração
3. **Logging Estruturado**: Integrar com `structlog` para melhor rastreamento
4. **Eventos de Domínio**: Implementar pattern de eventos para notificações assíncronas
5. **Use Cases**: Extrair `SendNotificationUseCase` se houver múltiplos fluxos

## Referências

- Clean Architecture: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- SOLID: https://en.wikipedia.org/wiki/SOLID
- Repository Pattern: https://martinfowler.com/eaaCatalog/repository.html
- Dependency Injection: https://en.wikipedia.org/wiki/Dependency_injection

