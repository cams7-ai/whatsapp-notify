# WhatsApp Notify

API REST em Python 3.12 para controlar uma sessão do WhatsApp Web e enviar mensagens usando FastAPI e Playwright.

A aplicação usa um perfil persistente do Chromium para reutilizar a sessão autenticada. Na primeira execução, ou quando a sessão expirar, será necessário escanear o "QR Code" no WhatsApp Web.

## Arquitetura

O projeto segue Clean Architecture com separação entre API, aplicação, domínio e infraestrutura.

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
LOG_LEVEL=INFO
```

Variáveis principais:

- `WHATSAPP_TARGET_NAME`: contato ou grupo usado quando `contact` não for enviado na requisição.
- `WHATSAPP_MESSAGE`: mensagem usada quando `message` não for enviada na requisição.
- `WHATSAPP_HEADLESS`: use `false` na primeira autenticação para visualizar o "QR Code".
- `WHATSAPP_PROFILE_DIR`: diretório do perfil persistente do Chromium.
- `WHATSAPP_TIMEOUT_SECONDS`: timeout máximo para autenticação, busca e envio.
- `API_HOST`: host do servidor FastAPI.
- `API_PORT`: porta do servidor FastAPI.
- `LOG_LEVEL`: nível minimo de "log" da aplicação (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

## Execução

```bash
python -m main
```

Ou, apos instalar o pacote:

```bash
whatsapp-notify
```

## API

### Iniciar sessão

```http
GET /whatsapp/session/start?headless=false&timeoutInSecounds=60
```

Abre o navegador e mantém a sessão ativa. Se for necessario autenticar, o navegador fica na tela do "QR Code" para que `/whatsapp/session/qrcode` possa retornar a imagem. Se `headless` não for informado, a API usa `WHATSAPP_HEADLESS`. Se `timeoutInSecounds` não for informado, a API usa `WHATSAPP_TIMEOUT_SECONDS`.

### Capturar QR Code

```http
GET /whatsapp/session/qrcode
```

Usa a sessão do WhatsApp Web já aberta, captura o QR Code visivel e retorna a imagem em PNG. Funciona com sessoes abertas em `headless=false` e `headless=true`. Se não houver sessão aberta, retorna o mesmo erro de `/whatsapp/messages/send`: `SESSAO_FECHADA`. Se a sessão existir, mas o "QR Code" não estiver disponivel, retorna erro JSON com `QR_CODE_NAO_ENCONTRADO`.

A captura do "QR Code" usa uma espera curta para não bloquear a requisição pelo timeout completo da sessão.

Headers relevantes da resposta:

- `Content-Type: image/png`
- `X-QRCode-Expires-In-Seconds`: janela estimada de validade do "QR Code", em segundos.
- `X-QRCode-Expires-At`: data/hora UTC estimada de expiração do "QR Code".
- `Cache-Control: no-store`

### Consultar status da sessão

```http
GET /whatsapp/session/status
```

Consulta o estado atual da sessão sem abrir navegador, fechar navegador, capturar imagem do QR Code, aguardar autenticação completa ou executar envio.

Respostas possíveis:

```json
{
  "status": "SESSAO_FECHADA",
  "message": "Sessão do WhatsApp Web fechada.",
  "isOpen": false
}
```

```json
{
  "status": "INICIANDO_SESSAO",
  "message": "Sessão do WhatsApp Web iniciando.",
  "isOpen": false
}
```

```json
{
  "status": "AGUARDANDO_AUTENTICACAO",
  "message": "Aguardando autenticação do WhatsApp Web.",
  "isOpen": true
}
```

```json
{
  "status": "CARREGANDO_CONVERSAS",
  "message": "Carregando conversas do WhatsApp Web.",
  "isOpen": true
}
```

```json
{
  "status": "SESSAO_ABERTA",
  "message": "Sessão do WhatsApp Web aberta.",
  "isOpen": true
}
```

### Enviar mensagem com sessão aberta

```http
POST /whatsapp/messages/send
Content-Type: application/json
```

Envia mensagem usando uma sessão já aberta e autenticada. Não abre nem fecha o navegador.

### Encerrar sessão

```http
GET /whatsapp/session/stop
```

Fecha a sessão ativa e o navegador associado.

Corpo aceito pelos endpoints de envio:

```json
{
  "contact": "Grupo Teste",
  "message": "Ola pelo WhatsApp Notify"
}
```

`contact` e `message` sao opcionais se os valores equivalentes estiverem configurados no `.env`.

O campo `headless` e aceito apenas em `GET /whatsapp/session/start`. O endpoint de envio usa sempre a sessão já aberta.

Resposta de envio:

```json
{
  "status": "enviado",
  "message": "Mensagem enviada com sucesso.",
  "contact": "Grupo Teste",
  "elapsedTimeInSeconds": 3.21
}
```

Resposta de sessão:

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

Documentação gerada pelo FastAPI:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## Testes

```bash
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing -q
```

Os testes nunca devem acessar a página oficial do WhatsApp Web; use mocks, fakes ou paginas virtuais para simular qualquer comportamento do navegador.

O relatorio de cobertura exige 100% dos modulos unit-testáveis em `src`. A automação Playwright (`src/whatsapp_service.py`) e entrypoints de execução são excluídos da metrica por dependerem de navegador real ou bootstrap do processo.

## Observações Operacionais

- O envio e confirmado depois que o WhatsApp Web aceita visualmente a mensagem ou esvazia o compositor sem erro/pendencia visivel.
- Os endpoints de sessão mantém um navegador ativo no processo da API.
- Os envios são serializados por processo para evitar disputa pelo mesmo perfil persistente.
- Use apenas um worker por instância quando compartilhar o mesmo `WHATSAPP_PROFILE_DIR`.
- Mudanças na "interface" do WhatsApp Web podem exigir atualizacao de seletores em `src/whatsapp_service.py`.
- A automação usa WhatsApp Web diretamente no navegador; não usa bibliotecas não oficiais baseadas em engenharia reversa do WhatsApp.
