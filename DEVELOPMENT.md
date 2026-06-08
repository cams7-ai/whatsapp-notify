# Guia de Desenvolvimento

## Instalar Dependencias

```bash
pip install -e ".[dev]"
```

Isso instala a aplicacao em modo editavel e inclui `pytest` e `pytest-cov`.

## Rodar Testes

```bash
pytest tests/ -v
```

Com cobertura:

```bash
pytest tests/ --cov=src --cov-report=term-missing
```

No Windows, se o Python global nao tiver `pytest`, use o ambiente virtual local:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

## Estrutura de Testes

```text
tests/
|-- test_logger.py
|-- test_pages.py
|-- test_playwright_notification_repository.py
|-- test_server_helpers.py
|-- test_services.py
`-- test_coverage_marker.py
```

## Adicionar Novo Teste

1. Crie um arquivo `test_*.py` em `tests/`.
2. Use mocks para dependencias externas como Playwright, navegador e repositorios.
3. Teste dominio e servicos sem subir FastAPI quando o comportamento for interno.
4. Teste API apenas quando precisar validar contrato HTTP.

Exemplo:

```python
from unittest.mock import Mock

from services import NotificationService


def test_service_sends_notification():
    repository = Mock()
    logger = Mock()
    service = NotificationService(repository, logger)

    service.send("Grupo", "Ola")

    repository.send.assert_called_once_with("Grupo", "Ola")
```

## Estender a Arquitetura

### Novo Repositorio

1. Crie `src/repositories/twilio_repository.py`.
2. Implemente `INotificationRepository`.
3. Converta erros externos para excecoes de dominio.
4. Ajuste a factory que seleciona o repositorio.

```python
from repositories import INotificationRepository


class TwilioNotificationRepository(INotificationRepository):
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

    def send(self, target_name: str, message: str) -> None:
        # Integracao Twilio aqui.
        pass
```

### Nova Pagina POM

1. Em `src/pages/pages.py`, crie uma classe baseada em `IBasePage`.
2. Coloque seletores como atributos privados da classe.
3. Exponha metodos de alto nivel, como `open_status()` ou `find_message_box()`.
4. Exporte a nova classe em `src/pages/__init__.py`.

```python
from pages.i_base_page import IBasePage


class StatusPage(IBasePage):
    _status_selectors = (...)

    def open_status(self) -> None:
        status_button = self._first_visible_locator(self._status_selectors, timeout_ms=5000)
        if status_button is None:
            raise RuntimeError("Status nao encontrado")
        status_button.click()
```

### Novo Modelo de Dominio

1. Crie ou edite arquivos em `src/domain/`.
2. Evite dependencias de FastAPI, Playwright ou variaveis de ambiente.
3. Cubra validacoes com testes unitarios.

## Tratamento de Erros

- Erros de dominio ficam em `src/domain/exceptions/`.
- Erros HTTP ficam na camada `src/api/`.
- Adaptadores devem capturar erros externos e converter para erros da aplicacao.

## Logging

Use o logger configurado em `src/logger.py` e injete nas classes que precisam registrar eventos.

```python
from logger import configure_logger

logger = configure_logger()
logger.info("Mensagem informativa")
```

## Regras Praticas

- Nao coloque seletores de UI em servicos de dominio.
- Nao acesse FastAPI dentro de `domain/` ou `services/`.
- Use Page Objects para interacoes de Playwright reutilizaveis.
- Mantenha testes de Playwright com fakes/mocks sempre que possivel.
- Use apenas um worker por instancia quando compartilhar o mesmo perfil do Chromium.
