# WhatsApp Notify

API REST em Python 3.12 para enviar mensagens pelo WhatsApp Web usando FastAPI e Playwright.

O projeto usa um perfil persistente do Chromium para reutilizar a sessão autenticada. Na primeira execução, ou quando a sessão expirar, será necessário escanear o QR Code do WhatsApp Web.

## Instalação

### Criar ambiente virtual

```bash
python -m venv .venv
```

### Ativar ambiente

```bash
.venv\Scripts\Activate.ps1
```

### Instalar dependências

```bash
pip install -e .
```

### Instalar os navegadores do Playwright

```bash
playwright install chromium
```

## Configuração

Crie um arquivo `.env` com base em `.env.example`.

Exemplo:

```env
WHATSAPP_TARGET_NAME=Grupo Teste
WHATSAPP_MESSAGE=Mensagem enviada automaticamente
WHATSAPP_HEADLESS=false
WHATSAPP_PROFILE_DIR=.whatsapp-profile
WHATSAPP_TIMEOUT_SECONDS=60
API_HOST=0.0.0.0
API_PORT=8000
```

Variáveis:

- `WHATSAPP_TARGET_NAME`: nome exato do contato individual ou grupo usado quando `contact` não for enviado no corpo da requisição.
- `WHATSAPP_MESSAGE`: mensagem usada quando `message` não for enviada no corpo da requisição.
- `WHATSAPP_HEADLESS`: use `false` para abrir o navegador visível, recomendado no Windows e na primeira autenticação.
- `WHATSAPP_PROFILE_DIR`: diretório do perfil persistente do Chromium.
- `WHATSAPP_TIMEOUT_SECONDS`: tempo máximo para autenticação, busca e envio.
- `API_HOST`: host usado pelo servidor FastAPI. Valor padrão: `0.0.0.0`.
- `API_PORT`: porta usada pelo servidor FastAPI. Valor padrão: `8000`.

## Execução

```bash
python -m app.main
```

Também é possível usar o comando instalado:

```bash
whatsapp-notify
```

## Documentação da API

Com a aplicação em execução, use os recursos gerados automaticamente pelo FastAPI:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

O Swagger UI permite testar o `POST /notifications` pelo navegador. O ReDoc oferece uma visualização mais estável para leitura do contrato. O OpenAPI JSON pode ser importado em ferramentas como Postman, Insomnia ou geradores de clientes HTTP.

Para consultar o contrato OpenAPI pelo terminal:

```text
http://localhost:8000/openapi.json
```

## Endpoint

### Enviar mensagem

```http
POST /notifications
Content-Type: application/json
```

Corpo da requisição:

```json
{
  "contact": "Grupo Teste",
  "message": "Mensagem enviada pela API"
}
```

Os campos `contact` e `message` são opcionais. Quando algum deles não for enviado, a API usará os valores das variáveis `WHATSAPP_TARGET_NAME` e `WHATSAPP_MESSAGE`.

Exemplo usando apenas as variáveis de ambiente:

```json
{}
```

Resposta de sucesso:

```json
{
  "status": "enviado",
  "message": "Mensagem enviada com sucesso.",
  "contact": "Grupo Teste",
  "elapsedTimeInSeconds": 12.345
}
```

## Tratamento de Erros

As respostas de erro seguem o formato:

```json
{
  "error": {
    "code": "DADOS_OBRIGATORIOS_AUSENTES",
    "message": "Informe 'contact' no corpo da requisição ou configure WHATSAPP_TARGET_NAME no ambiente",
    "fields": ["contact"]
  }
}
```

Status HTTP usados:

- `400`: corpo inválido, campos efetivos ausentes ou contato/grupo não encontrado.
- `500`: configuração inválida do servidor, timeout de autenticação, falha na automação do Chromium ou erro inesperado.

## Tempo de Resposta

O `POST /notifications` responde somente depois que o Playwright finaliza a tentativa de envio. Em autenticações novas, a requisição pode ficar aberta enquanto o QR Code é escaneado.

A resposta de sucesso inclui `elapsedTimeInSeconds`, medido desde o início do processamento da requisição até a confirmação do envio. Esse tempo inclui a execução do Playwright e eventual espera na fila interna de envio.

A API retorna sucesso depois que o WhatsApp Web confirma visualmente a mensagem como enviada, entregue ou lida. Quando o WhatsApp Web virtualiza a lista e não mantém a nova bolha acessível no DOM, a API aceita como sucesso o campo de composição vazio de forma estável, desde que não exista erro ou pendência visível. Se a mensagem ficar pendente, se houver erro explícito ou se o campo continuar preenchido até o timeout, a API retorna erro `500`.

A execução do Playwright roda fora do event loop da FastAPI para manter a API responsiva durante o uso do Chromium. Os envios são serializados por processo para evitar disputa pelo mesmo perfil persistente do navegador.

Se publicar a API atrás de proxy, gateway ou load balancer, configure o timeout da chamada HTTP com margem maior que `WHATSAPP_TIMEOUT_SECONDS`.

Use apenas um worker por instância quando o mesmo `WHATSAPP_PROFILE_DIR` for compartilhado.

## Observações

- Na primeira execução será necessário escanear o QR Code.
- As sessões serão reutilizadas automaticamente pelo perfil persistente.
- Não apague o diretório definido em `WHATSAPP_PROFILE_DIR` se quiser manter a sessão.
- Mudanças na interface do WhatsApp Web podem exigir atualização dos seletores do Playwright em `src/app/whatsapp_service.py`.
- A automação usa WhatsApp Web diretamente no navegador; não usa bibliotecas não oficiais baseadas em engenharia reversa do WhatsApp.
