# Guia de Desenvolvimento

## Instalar Dependencias

```powershell
pip install -e ".[dev]"
```

Isso instala a aplicacao em modo editavel e inclui `pytest` e `pytest-cov`.

## Rodar Testes

```powershell
pytest tests/ -v
```

Com relatorio de cobertura:

```powershell
pytest --cov=src --cov-report=term-missing -q
```

No Windows, se o Python global nao tiver `pytest`, use o ambiente virtual local:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing -q
```

## Regras para Testes

- Nunca acesse `https://web.whatsapp.com` durante testes automatizados.
- Simule Playwright e WhatsApp Web com mocks, fakes ou paginas virtuais.
- Cubra novos endpoints, handlers e serviços com testes isolados.
- Mantenha 100% de cobertura nos modulos unit-testáveis medidos em `src`.
- A automação Playwright e entrypoints de bootstrap ficam fora da metrica de cobertura por exigirem navegador real ou processo em execução.

## Estrutura de Testes

```text
tests/
|-- test_notification_handler_session.py
|-- test_server_helpers.py
|-- test_services.py
|-- test_whatsapp_routes.py
`-- test_whatsapp_session_service.py
```

## Fluxos Principais

- `GET /whatsapp/session/start`: abre sessão persistente.
- `POST /whatsapp/messages/send`: envia usando sessão aberta.
- `GET /whatsapp/session/stop`: fecha sessão persistente.

## Regras Práticas

- Não coloque seletores de UI em serviços de dominio.
- Não acesse FastAPI dentro de `domain/` ou `services/`.
- Handlers devem delegar logica aos serviços.
- Use apenas um worker por instância quando compartilhar o mesmo perfil do Chromium.
