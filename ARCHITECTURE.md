# Arquitetura do WhatsApp Notify

## Visao Geral

A aplicação segue Clean Architecture com separação clara entre API, aplicação, domínio e infraestrutura. A API controla uma sessão persistente do WhatsApp Web para multiplos envios.

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
|-- config.py                    # Configuração via ambiente
|-- domain/                      # Modelos e exceções de dominio
|-- main.py                      # Entry point da aplicação
|-- services/                    # Orquestração de negocio e sessão
`-- whatsapp_service.py          # Automação Playwright base e sessão persistente
```

## Responsabilidades

- `domain/`: contem regras puras, modelos e exceções sem dependência de FastAPI ou Playwright.
- `services/`: valida e orquestra casos de uso, incluindo `WhatsAppSessionService`.
- `api/`: traduz HTTP para chamadas de aplicação e mapeia erros para respostas.
- `whatsapp_service.py`: centraliza a automação Playwright, seletores e sessão persistente.

## Fluxos

### Sessao persistente

1. Cliente chama `GET /whatsapp/session/start`.
2. `WhatsAppSessionService` cria `PersistentWhatsAppSession`.
3. A sessão abre o navegador e mantém a página disponivel.
4. Cliente chama `POST /whatsapp/messages/send` para enviar usando a sessão aberta.
5. Cliente chama `GET /whatsapp/session/stop` para fechar navegador e sessão.

## Mapeamento de Erros

| Erro de dominio | HTTP | Código                     |
| --- | --- |----------------------------|
| `SessionAlreadyOpenError` | 400 | `SESSAO_JA_ABERTA`         |
| `SessionClosedError` | 400 | `SESSAO_FECHADA`           |
| `TargetNotFoundError` | 400 | `DESTINO_NAO_ENCONTRADO`   |
| `AuthenticationError` | 500 | `AUTENTICACAO_EXPIRADA`    |
| `SessionStartError` | 500 | `FALHA_AO_INICIAR_SESSAO`  |
| `SessionStopError` | 500 | `FALHA_AO_ENCERRAR_SESSAO` |
| `SendError` | 500 | `FALHA_NO_ENVIO`           |
| `DomainError` | 500 | `FALHA_NA_AUTOMACAO`       |
| erro inesperado | 500 | `ERRO_INTERNO`             |

## Regras de Manutencao

- Não coloque seletor de Playwright em `domain/` ou `services/`.
- Handlers HTTP devem coordenar entrada, saída e chamadas aos serviços.
- Prefira mensagens de erro de domínio nas camadas internas e mapeamento HTTP apenas em `api/`.
- Testes nunca devem chamar a página oficial do WhatsApp Web; use mocks, fakes ou paginas virtuais.
