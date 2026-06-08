# Arquitetura do WhatsApp Notify

## Visao Geral

A aplicacao segue Clean Architecture com separacao clara entre API, aplicacao, dominio e infraestrutura. A API pode executar o envio completo em uma unica chamada ou controlar uma sessao persistente do WhatsApp Web para multiplos envios.

## Camadas

```text
Presentation  -> src/api/, src/main.py
Application   -> src/services/
Domain        -> src/domain/
Infrastructure-> src/whatsapp_service.py
```

## Estrutura Atual

```text
src/
|-- api/                         # Rotas, handlers, schemas e OpenAPI
|-- config.py                    # Configuracao via ambiente
|-- domain/                      # Modelos e excecoes de dominio
|-- main.py                      # Entry point da aplicacao
|-- services/                    # Orquestracao de negocio e sessao
`-- whatsapp_service.py          # Automacao Playwright base e sessao persistente
```

## Responsabilidades

- `domain/`: contem regras puras, modelos e excecoes sem dependencia de FastAPI ou Playwright.
- `services/`: valida e orquestra casos de uso, incluindo `WhatsAppNotificationService` e `WhatsAppSessionService`.
- `api/`: traduz HTTP para chamadas de aplicacao e mapeia erros para respostas.
- `whatsapp_service.py`: centraliza a automacao Playwright, seletores e sessao persistente.

## Fluxos

### Envio completo

1. Cliente chama `POST /whatsapp/messages/send-and-close`.
2. A API valida payload e carrega configuracao.
3. `WhatsAppNotificationService` valida a notificacao e chama `WhatsAppService`.
4. `WhatsAppService` abre o navegador, autentica, envia e fecha.
5. Erros de automacao sao convertidos para erros de dominio/API.

### Sessao persistente

1. Cliente chama `GET /whatsapp/session/start`.
2. `WhatsAppSessionService` cria `PersistentWhatsAppSession`.
3. A sessao abre o navegador, autentica e mantem a pagina pronta.
4. Cliente chama `POST /whatsapp/messages/send` para enviar usando a sessao aberta.
5. Cliente chama `GET /whatsapp/session/stop` para fechar navegador e sessao.

## Mapeamento de Erros

| Erro de dominio | HTTP | Codigo |
| --- | --- | --- |
| `SessionAlreadyOpenError` | 400 | `SESSAO_JA_ABERTA` |
| `SessionClosedError` | 400 | `SESSAO_FECHADA` |
| `TargetNotFoundError` | 400 | `DESTINO_NAO_ENCONTRADO` |
| `AuthenticationError` | 500 | `AUTENTICACAO_EXPIRADA` |
| `SessionStartError` | 500 | `FALHA_AO_INICIAR_SESSAO` |
| `SessionStopError` | 500 | `FALHA_AO_ENCERRAR_SESSAO` |
| `SendError` | 500 | `FALHA_NO_ENVIO` |
| `DomainError` | 500 | `FALHA_NA_AUTOMACAO` |
| erro inesperado | 500 | `ERRO_INTERNO` |

## Regras de Manutencao

- Nao coloque seletor de Playwright em `domain/` ou `services/`.
- Handlers HTTP devem coordenar entrada, saida e chamadas aos servicos.
- Prefira mensagens de erro de dominio nas camadas internas e mapeamento HTTP apenas em `api/`.
- Testes nunca devem chamar a pagina oficial do WhatsApp Web; use mocks, fakes ou paginas virtuais.
