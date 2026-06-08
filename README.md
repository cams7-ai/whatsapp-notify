# WhatsApp Notify

API REST em Python 3.12 para controlar uma sessao do WhatsApp Web e enviar mensagens usando FastAPI e Playwright.

A aplicacao usa um perfil persistente do Chromium para reutilizar a sessao autenticada. Na primeira execucao, ou quando a sessao expirar, sera necessario escanear o QR Code no WhatsApp Web.

## Arquitetura

O projeto segue Clean Architecture com separacao entre API, aplicacao, dominio e infraestrutura.

```text
Presentation  -> src/api/, src/main.py
Application   -> src/services/
Domain        -> src/domain/
Infrastructure-> src/whatsapp_service.py
```

Detalhes completos ficam em [ARCHITECTURE.md](./ARCHITECTURE.md).

## Requisitos

- Python 3.12+
- Chromium instalado pelo Playwright
- Uma conta WhatsApp com acesso ao WhatsApp Web

## Instalacao

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

Em Linux/macOS, adapte a ativacao do ambiente virtual:

```bash
source .venv/bin/activate
```

## Configuracao

Crie um arquivo `.env` a partir de `.env.example`.

```env
WHATSAPP_TARGET_NAME=Grupo Teste
WHATSAPP_MESSAGE=Mensagem enviada automaticamente
WHATSAPP_HEADLESS=false
WHATSAPP_PROFILE_DIR=.whatsapp-profile
WHATSAPP_TIMEOUT_SECONDS=60
API_HOST=0.0.0.0
API_PORT=8000
```

Variaveis principais:

- `WHATSAPP_TARGET_NAME`: contato ou grupo usado quando `contact` nao for enviado na requisicao.
- `WHATSAPP_MESSAGE`: mensagem usada quando `message` nao for enviada na requisicao.
- `WHATSAPP_HEADLESS`: use `false` na primeira autenticacao para visualizar o QR Code.
- `WHATSAPP_PROFILE_DIR`: diretorio do perfil persistente do Chromium.
- `WHATSAPP_TIMEOUT_SECONDS`: timeout maximo para autenticacao, busca e envio.
- `API_HOST`: host do servidor FastAPI.
- `API_PORT`: porta do servidor FastAPI.

## Execucao

```bash
python -m main
```

Ou, apos instalar o pacote:

```bash
whatsapp-notify
```

## API

### Iniciar sessao

```http
GET /whatsapp/session/start?headless=false
```

Abre o navegador, aguarda autenticacao quando necessario e mantem a sessao ativa. Se `headless` nao for informado, a API usa `WHATSAPP_HEADLESS`.

### Enviar mensagem com sessao aberta

```http
POST /whatsapp/messages/send
Content-Type: application/json
```

Envia mensagem usando uma sessao ja aberta e autenticada. Nao abre nem fecha o navegador.

### Encerrar sessao

```http
GET /whatsapp/session/stop
```

Fecha a sessao ativa e o navegador associado.

### Enviar mensagem e fechar

```http
POST /whatsapp/messages/send-and-close
Content-Type: application/json
```

Mantem o comportamento antigo de `POST /notifications`: abre o WhatsApp Web, autentica quando necessario, envia a mensagem e fecha o navegador.

Corpo aceito pelos endpoints de envio:

```json
{
  "contact": "Grupo Teste",
  "message": "Ola pelo WhatsApp Notify",
  "headless": false
}
```

`contact` e `message` sao opcionais se os valores equivalentes estiverem configurados no `.env`. `headless` e opcional e sobrescreve `WHATSAPP_HEADLESS` apenas no fluxo que abre navegador.

Resposta de envio:

```json
{
  "status": "enviado",
  "message": "Mensagem enviada com sucesso.",
  "contact": "Grupo Teste",
  "elapsedTimeInSeconds": 3.21
}
```

Resposta de sessao:

```json
{
  "status": "ok",
  "message": "Sessao do WhatsApp Web iniciada com sucesso."
}
```

Resposta de erro:

```json
{
  "error": {
    "code": "SESSAO_FECHADA",
    "message": "A sessao do WhatsApp Web esta fechada. Inicie a sessao antes de enviar mensagens."
  }
}
```

Documentacao gerada pelo FastAPI:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Testes

```bash
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing -q
```

Os testes nunca devem acessar a pagina oficial do WhatsApp Web; use mocks, fakes ou paginas virtuais para simular qualquer comportamento do navegador.

## Observacoes Operacionais

- O envio e confirmado depois que o WhatsApp Web aceita visualmente a mensagem ou esvazia o compositor sem erro/pendencia visivel.
- Os endpoints de sessao mantem um navegador ativo no processo da API.
- Os envios sao serializados por processo para evitar disputa pelo mesmo perfil persistente.
- Use apenas um worker por instancia quando compartilhar o mesmo `WHATSAPP_PROFILE_DIR`.
- Mudancas na interface do WhatsApp Web podem exigir atualizacao de seletores em `src/whatsapp_service.py`.
- A automacao usa WhatsApp Web diretamente no navegador; nao usa bibliotecas nao oficiais baseadas em engenharia reversa do WhatsApp.
