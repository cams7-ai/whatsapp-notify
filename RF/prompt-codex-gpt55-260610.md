# Prompt Codex GPT-5.5 - Endpoint de status da sessão WhatsApp Web

## Contexto

Você está trabalhando no projeto `whatsapp-notify`, uma API REST em Python 3.12 com FastAPI e Playwright que controla uma sessão persistente do WhatsApp Web.

A aplicação segue Clean Architecture:

```text
Presentation  -> src/api/, src/main.py
Application   -> src/services/
Domain        -> src/domain/
Infrastructure-> src/whatsapp_service.py
```

Fluxo atual relevante:

- `python -m main` inicia o servidor FastAPI, mas não abre o navegador automaticamente.
- `GET /whatsapp/session/start` cria uma `PersistentWhatsAppSession`, abre um contexto persistente do Chromium e navega para `https://web.whatsapp.com`.
- `GET /whatsapp/session/start` não deve aguardar autenticação completa. O teste existente `test_persistent_session_start_does_not_wait_for_authentication` garante esse comportamento.
- `GET /whatsapp/session/qrcode` usa a sessão já aberta para capturar o "QR Code" visível e não deve abrir nem fechar sessão.
- `POST /whatsapp/messages/send` exige sessão aberta, aguarda autenticação, abre a conversa e envia a mensagem. Não deve abrir nem fechar o navegador.
- `GET /whatsapp/session/stop` fecha a sessão ativa e remove a referência interna quando a sessão for encerrada.
- `WhatsAppSessionService` guarda a sessão ativa em `self._session` e expõe `is_open` com base em `PersistentWhatsAppSession.is_open`.
- `PersistentWhatsAppSession` encapsula `_page`, `_context` e `_playwright`; qualquer inspeção real da tela do WhatsApp Web deve ficar nessa camada ou em `WhatsAppService`, não em handlers HTTP.

## Objetivo

Crie o endpoint:

```http
GET /whatsapp/session/status
```

Esse endpoint deve retornar o status atual da aplicação "WhatsApp Notify" em relação à sessão do "WhatsApp Web", sem alterar o estado da sessão, sem abrir navegador, sem fechar navegador, sem aguardar autenticação completa e sem executar fluxo de envio.

## Contrato HTTP

O endpoint deve responder sempre com HTTP 200 quando a consulta for realizada com sucesso.

Formato da resposta JSON:

```json
{
  "status": "SESSAO_FECHADA",
  "message": "Sessão do WhatsApp Web fechada.",
  "isOpen": false
}
```

Campos:

- `status`: string com um dos status definidos abaixo.
- `message`: mensagem em português correspondente ao status.
- `isOpen`: booleano indicando se existe navegador/sessão Playwright aberta no processo.

Use alias Pydantic para expor `isOpen` em JSON, mantendo nome Python idiomático se desejar, por exemplo `is_open`.

## Estados esperados

### 1. Sessão fechada

Quando a aplicação acabou de iniciar com `python -m main` e nenhum endpoint de start foi chamado ainda:

```http
Status: 200
```

```json
{
  "status": "SESSAO_FECHADA",
  "message": "Sessão do WhatsApp Web fechada.",
  "isOpen": false
}
```

Também deve retornar esse mesmo status apos `GET /whatsapp/session/stop` encerrar a sessão.

### 2. Iniciando sessão

Apos chamar `GET /whatsapp/session/start`, enquanto o navegador/pagina ainda estiver abrindo, carregando `https://web.whatsapp.com`, ou antes, de ser possível identificar "QR Code", tela de carregamento de conversas ou tela principal autenticada:

```http
Status: 200
```

```json
{
  "status": "INICIANDO_SESSAO",
  "message": "Sessão do WhatsApp Web iniciando.",
  "isOpen": false
}
```

Observação importante: na implementação atual, `GET /whatsapp/session/start` só atribui `self._session` em `WhatsAppSessionService` depois que `session.start()` termina. Se a API usa o lock atual durante `start`, talvez o endpoint `status` so consiga ser atendido após o lock liberar. Ainda assim, modele o estado de forma correta para não depender desse detalhe. Se for necessario rastrear uma tentativa de abertura em andamento, use estado explicito no serviço de sessão, sem substituir a sessão ativa prematuramente por uma sessão inconsistente.

### 3. Aguardando autenticação

Quando a sessão Playwright estiver aberta e a tela de autenticação estiver exibindo o "QR Code" para o usuário escanear com o celular, ou seja, quando os seletores de "QR Code" estiverem visíveis:

```http
Status: 200
```

```json
{
  "status": "AGUARDANDO_AUTENTICACAO",
  "message": "Aguardando autenticação do WhatsApp Web.",
  "isOpen": true
}
```

Detecte esse estado usando os seletores de "QR Code" já existentes em `WhatsAppService._qr_code_selectors`, ou uma funcao reutilizável equivalente em `WhatsAppService`.

### 4. Carregando conversas

Quando o usuário já autenticou ou já possui perfil autenticado, mas o WhatsApp Web continua exibindo a etapa de carregamento das conversas, por exemplo, texto semelhante a "Carregando suas conversas" ou "Loading your chats":

```http
Status: 200
```

```json
{
  "status": "CARREGANDO_CONVERSAS",
  "message": "Carregando conversas do WhatsApp Web.",
  "isOpen": true
}
```

Inclua detecção robusta para português e inglês, preferencialmente por texto visível e/ou seletores pouco acoplados. Não coloque seletores Playwright na camada `api` nem em `domain`.

### 5. Sessão aberta

Quando a tela principal do WhatsApp Web estiver aberta e pronta para envio, isto e, quando algum seletor autenticado usado atualmente pela automação estiver visivel:

```http
Status: 200
```

```json
{
  "status": "SESSAO_ABERTA",
  "message": "Sessão do WhatsApp Web aberta.",
  "isOpen": true
}
```

Reaproveite `WhatsAppService._authenticated_selectors` ou uma função de consulta criada a partir desses seletores.

## Regras de comportamento

- `GET /whatsapp/session/status` deve ser somente leitura.
- `GET /whatsapp/session/status` não pode abrir navegador.
- `GET /whatsapp/session/status` não pode fechar navegador.
- `GET /whatsapp/session/status` não pode chamar `_wait_for_authentication`, `_open_target_conversation` ou `_send_configured_message`.
- `GET /whatsapp/session/status` não pode capturar "QR Code" como imagem nem alterar headers/cache do endpoint `/qrcode`.
- Consultar `/whatsapp/session/status` repetidamente não deve alterar o status, exceto se a propria página do WhatsApp Web tiver mudado de estado entre as consultas.
- Consultar `/whatsapp/session/qrcode` não deve alterar o status, exceto se a propria página do WhatsApp Web tiver mudado de estado.
- Chamar `/whatsapp/messages/send` não deve alterar artificialmente o status. Após envio bem-sucedido, se a tela principal continuar aberta, `/status` deve retornar `SESSAO_ABERTA`.
- O comportamento dos endpoints existentes `/whatsapp/session/start`, `/whatsapp/session/qrcode`, `/whatsapp/messages/send` e `/whatsapp/session/stop` não pode regredir.
- Preserve o padrão de erros existente da API. O endpoint de status, quando não houver sessão, deve retornar `SESSAO_FECHADA` com HTTP 200, não erro `SESSAO_FECHADA`.

## Orientação de implementação

Implemente a mudanca mantendo a separação de camadas:

1. Dominio/modelo de status

Crie uma representação clara para os status de sessão, por exemplo, um `Enum` ou dataclass em `domain` ou `services`, contendo:

- `SESSAO_FECHADA`
- `INICIANDO_SESSAO`
- `AGUARDANDO_AUTENTICACAO`
- `CARREGANDO_CONVERSAS`
- `SESSAO_ABERTA`

Associe cada status a sua mensagem oficial.

2. Infraestrutura Playwright

Adicione em `PersistentWhatsAppSession` um método consultivo, por exemplo `status()` ou `get_status()`, que:

- retorna fechado/iniciando se `_page`, `_context` ou `_playwright` não estiverem disponíveis;
- consulta a página atual com timeouts curtos;
- identifica primeiro a tela principal autenticada, depois "QR Code", depois carregamento de conversas, ou use uma ordem tecnicamente justificada que evite falso positivo;
- retorna `INICIANDO_SESSAO` quando a sessão está aberta, mas nenhum estado conhecido foi identificado ainda.

Evite esperas longas. Status deve ser rapido e não bloquear pelo timeout completo configurado em `WHATSAPP_TIMEOUT_SECONDS`.

3. Serviço de aplicação

Adicione em `WhatsAppSessionService` um método consultivo, por exemplo `status()` ou `get_status()`, que:

- retorna `SESSAO_FECHADA` quando `self._session` for `None` ou quando `self._session.is_open` for falso;
- delega a inspeção da página para `PersistentWhatsAppSession` quando houver sessão aberta;
- não levanta `SessionClosedError` para sessão fechada;
- não altera `self._session`, salvo se for necessário limpar uma referência comprovadamente fechada/inválida de modo coerente com o padrao ja usado em `send`/`stop`.

Se você decidir rastrear estado `INICIANDO_SESSAO` explicitamente durante `start`, garanta que falhas de start limpem esse estado em `finally`.

4. API/handler/schema

Adicione:

- schema `SessionStatusResponse` em `src/api/schemas/notification_schema.py` ou arquivo equivalente;
- método `get_session_status` em `NotificationHandler`;
- rota `GET /whatsapp/session/status` em `src/api/routers/notification_router.py`;
- documentação OpenAPI com `response_model=SessionStatusResponse`, summary, description e operation_id coerentes.

O handler deve usar o mesmo lock apenas se isso for necessário para consistência interna. Não use lock de forma que uma consulta de status simples fique bloqueada por toda a autenticação ou envio, a menos que a estrutura atual exija isso para evitar corrida com Playwright. Se mantiver lock, explique nos testes/estrutura que a consulta continua sem efeitos colaterais.

5. README e arquitetura

Atualize o README para documentar o novo endpoint, com exemplos de resposta para cada status.

Se houver impacto arquitetural relevante, atualize `ARCHITECTURE.md` ou `DEVELOPMENT.md` de forma curta.

## Testes obrigatórios

Adicione ou ajuste testes sem acessar `https://web.whatsapp.com`.

Cubra no minimo:

- rota `/whatsapp/session/status` delegando para o handler e retornando JSON com `isOpen`;
- handler retornando status de sessão fechada com HTTP 200 via schema normal, não erro;
- `WhatsAppSessionService.status()` retornando `SESSAO_FECHADA` antes do start;
- `WhatsAppSessionService.status()` delegando para a sessão persistente quando aberta;
- `PersistentWhatsAppSession`/`WhatsAppService` identificando "QR Code" como `AGUARDANDO_AUTENTICACAO` usando fake/mocks;
- identificando tela principal autenticada como `SESSAO_ABERTA` usando fake/mocks;
- identificando carregamento de conversas como `CARREGANDO_CONVERSAS` usando fake/mocks;
- status não chamando `_wait_for_authentication`, `_open_target_conversation`, `_send_configured_message`, `capture_qr_code`, `start` ou `stop`;
- endpoints existentes continuam passando.

Rode:

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing -q
```

A cobertura configurada exige 100% para os modulos unit-testáveis em `src`; `src/whatsapp_service.py` está omitido da metrica de cobertura, mas ainda pode ter testes comportamentais com mocks quando fizer sentido.

## Criterios de aceite

- `GET /whatsapp/session/status` existe e aparece no OpenAPI.
- Com a aplicação recém-iniciada, retorna HTTP 200 com `SESSAO_FECHADA` e `isOpen: false`.
- Com sessão aberta exibindo "QR Code", retorna `AGUARDANDO_AUTENTICACAO` e `isOpen: true`.
- Com sessão aberta exibindo carregamento de conversas, retorna `CARREGANDO_CONVERSAS` e `isOpen: true`.
- Com tela principal pronta, retorna `SESSAO_ABERTA` e `isOpen: true`.
- Durante abertura/carregamento inicial sem estado identificável, retorna `INICIANDO_SESSAO`.
- Apos `/whatsapp/session/stop`, retorna `SESSAO_FECHADA` e `isOpen: false`.
- `/status`, `/qrcode` e `/messages/send` não produzem mudanca artificial de estado de status.
- Nenhum teste automatizado acessa WhatsApp Web real.
- Todos os testes passam com cobertura exigida.
