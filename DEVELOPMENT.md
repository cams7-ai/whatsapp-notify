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

Com relatorio de cobertura:

```bash
pytest --cov=src --cov-report=term-missing -q
```

No Windows, se o Python global nao tiver `pytest`, use o ambiente virtual local:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing -q
```

## Regras para Testes

- Nunca acesse `https://web.whatsapp.com` durante testes automatizados.
- Simule Playwright e WhatsApp Web com mocks, fakes ou paginas virtuais.
- Cubra novos endpoints, handlers e servicos com testes isolados.
- Mantenha cobertura relevante de `src` sem testes artificiais que apenas executem linhas.

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

- `GET /whatsapp/session/start`: abre sessao persistente.
- `POST /whatsapp/messages/send`: envia usando sessao aberta.
- `GET /whatsapp/session/stop`: fecha sessao persistente.
- `POST /whatsapp/messages/send-and-close`: executa o fluxo completo antigo de `/notifications`.

## Regras Praticas

- Nao coloque seletores de UI em servicos de dominio.
- Nao acesse FastAPI dentro de `domain/` ou `services/`.
- Handlers devem delegar logica aos servicos.
- Use apenas um worker por instancia quando compartilhar o mesmo perfil do Chromium.
