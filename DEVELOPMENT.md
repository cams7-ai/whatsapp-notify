# Guia de Desenvolvimento

## Instalar dependências de desenvolvimento

```bash
pip install -e ".[dev]"
```

Isto instala `pytest` e `pytest-cov` necessários para rodar testes.

## Rodar testes unitários

```bash
pytest tests/ -v
```

Com cobertura:

```bash
pytest tests/ --cov=src/app --cov-report=term-missing
```

## Estrutura de testes

```
tests/
├── test_services.py       # Testes do NotificationService
├── test_domain.py         # Testes do modelo Notification
├── test_repositories.py   # Testes do repositório (mocks)
└── test_main.py           # Testes de integração (endpoints)
```

## Adicionar novo teste

1. Crie arquivo `test_*.py` em `tests/`
2. Use fixtures do pytest para DI mockado
3. Use `unittest.mock.Mock` para mockar `NotificationRepository`

Exemplo:

```python
import pytest
from unittest.mock import Mock
from services import NotificationService


def test_service_sends_notification(self):
    mock_repo = Mock()
    service = NotificationService(mock_repo, Mock())

    service.send("Grupo", "Olá")

    mock_repo.send.assert_called_once_with("Grupo", "Olá")
```

## Estender a arquitetura

### Adicionar novo repositório (ex: Twilio)

1. Crie `src/app/repositories/twilio_repository.py`:

```python
from repositories import INotificationRepository


class TwilioNotificationRepository(INotificationRepository):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def send(self, target_name: str, message: str) -> None:
        # Lógica Twilio aqui
        pass
```

2. Em `src/app/main.py`, customize a factory de repositório:

```python
def _get_repository(config: AppConfig) -> NotificationRepository:
    repo_type = os.getenv("NOTIFICATION_REPO", "playwright")
    if repo_type == "twilio":
        return TwilioNotificationRepository(config, logger)
    return PlaywrightNotificationRepository(config, logger)

def _send_message(config: AppConfig) -> None:
    repository = _get_repository(config)
    service = NotificationService(repository, logger)
    service.send(config.target_name, config.message)
```

3. Teste a nova implementação mockando a interface:

```python
def test_twilio_repository_sends():
    from src import TwilioNotificationRepository

    repo = TwilioNotificationRepository(config, logger)
    # Não lança erro
    repo.send("Grupo", "Olá")
```

### Adicionar nova página (POM)

1. Em `src/app/pages/__init__.py`, adicione classe baseada em `BasePage`:

```python
class NewPage(BasePage):
    _selectors = (...)
    
    def some_action(self) -> None:
        # Use _first_visible_locator(), _is_any_selector_visible()
        pass
```

2. Use em `WhatsAppService` quando necessário:

```python
from pages import NewPage

# Em WhatsAppService.run()
new_page = NewPage(page, self.logger)
new_page.some_action()
```

### Adicionar novo modelo de domínio

1. Em `src/app/domain/__init__.py`, adicione:

```python
@dataclass(frozen=True)
class MyModel:
    field1: str
    field2: int
```

2. Use em services ou validação:

```python
from domain import MyModel

model = MyModel(field1="value", field2=123)
```

## Tratamento de erros

Exceções de domínio são mapeadas automaticamente em `main.py`:

```python
try:
    service.send(...)
except TargetNotFoundError:
    # → HTTP 400 + code DESTINO_NAO_ENCONTRADO
except AuthenticationError:
    # → HTTP 500 + code AUTENTICACAO_EXPIRADA
except SendError:
    # → HTTP 500 + code FALHA_NO_ENVIO
except DomainError:
    # → HTTP 500 + code FALHA_NA_AUTOMACAO
```

Para adicionar novo mapeamento:

```python
except MyCustomError as exc:
    raise ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="MEU_CODIGO_ERRO",
        message=str(exc),
    ) from exc
```

## Logging

O logger está disponível em toda aplicação:

```python
from logger import configure_logger

logger = configure_logger()

logger.info("Mensagem informativa")
logger.warning("Aviso")
logger.exception("Erro com stack trace")
```

## Próximas melhorias recomendadas

1. **Usar `dependency-injector`**: Automatizar DI
2. **Adicionar eventos de domínio**: Padrão para notificações assíncronas
3. **Usar casos de uso (Use Cases)**: Se precisar de múltiplos fluxos
4. **Integração contínua**: GitHub Actions para rodar testes
5. **Logging estruturado**: Integrar com `structlog`

