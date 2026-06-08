# Solicitação de Ajustes na Aplicação

## Contexto

Renomeei o endpoint atual `POST /notifications` para:

```http
POST /whatsapp/messages/send-and-close
```

O novo endpoint deve manter exatamente o comportamento atual de `/notifications`.

Arquivo de referência inicial:

```text
src/api/handlers/notification_handler.py
```

## Objetivo

Criar novos endpoints para controlar explicitamente a sessão do WhatsApp Web, reutilizando a lógica existente e evitando duplicação de código.

## Endpoints Necessários

### 1. Iniciar Sessão

```http
GET /whatsapp/session/start
```

Responsabilidades:

- Inicializar a sessão do WhatsApp Web.
- Abrir o navegador.
- Aguardar autenticação, caso necessário.
- Manter a sessão do WhatsApp Web aberta após autenticação.
- Retornar sucesso somente quando a página de envio de mensagens do WhatsApp Web estiver aberta e pronta para uso.

Parâmetros:

- `headless`: parâmetro opcional do tipo boolean.
- Caso `headless` não seja informado, usar o valor configurado em `WHATSAPP_HEADLESS`.

Tratamento de erros:

- Se já existir uma sessão aberta, retornar erro com mensagem personalizada.
- Se não for possível abrir a sessão, retornar erro com mensagem personalizada.

---

### 2. Enviar Mensagem com Sessão Aberta

```http
POST /whatsapp/messages/send
```

Responsabilidades:

- Enviar uma mensagem usando uma sessão do WhatsApp Web já aberta e autenticada.
- Não abrir uma nova sessão.
- Não fechar a sessão após o envio.

Payload:

- Utilizar o mesmo payload atualmente usado por `POST /notifications`.

Tratamento de erros:

- Se a sessão estiver fechada ou inexistente, retornar erro com mensagem personalizada.
- Se a sessão não estiver autenticada, retornar erro com mensagem personalizada.
- Se houver falha no envio, retornar erro com mensagem personalizada.

---

### 3. Encerrar Sessão

```http
GET /whatsapp/session/stop
```

Responsabilidades:

- Fechar a sessão ativa do WhatsApp Web.
- Fechar o navegador associado à sessão.

Tratamento de erros:

- Se a sessão já estiver fechada ou inexistente, retornar erro com mensagem personalizada.
- Se não for possível fechar a sessão ou o navegador, retornar erro com mensagem personalizada.

---

### 4. Enviar Mensagem e Encerrar Sessão

```http
POST /whatsapp/messages/send-and-close
```

Responsabilidades:

- Manter o comportamento atual do endpoint `POST /notifications`.
- Inicializar a sessão do WhatsApp Web.
- Abrir o navegador.
- Aguardar autenticação, caso necessário.
- Enviar a mensagem.
- Fechar a sessão ativa do WhatsApp Web.
- Fechar o navegador.

Payload:

- Utilizar o mesmo payload atualmente usado por `POST /notifications`.
- Adicionar suporte ao atributo opcional `headless`.

Requisito obrigatório:

- Garantir que o comportamento atual de `POST /notifications` seja preservado neste novo endpoint.

## Requisitos Técnicos

- Criar novas exceções personalizadas para os novos cenários de erro.
- Criar novas mensagens de erro específicas e claras.
- Mapear os erros para HTTP `400` ou `500`, conforme o contexto.
- Reutilizar código existente sempre que possível.
- Evitar duplicação de lógica entre os endpoints.
- Separar responsabilidades conforme a arquitetura atual da aplicação.
- Manter compatibilidade com o fluxo atual de envio.
- Atualizar testes existentes e criar novos testes para os novos fluxos.
- Criar novos testes para garantir cobertura de 100%.
- Nunca chamar a página oficial do WhatsApp Web durante os testes.
- Quando for necessário simular o WhatsApp Web nos testes, usar mock, página virtual, fake ou a melhor estratégia isolada para o cenário testado.
- Atualizar documentação da API e documentação do projeto.

## Requisitos de Qualidade

- O código deve ser legível e reutilizável.
- Os nomes de funções, classes e exceções devem expressar claramente a intenção.
- A lógica de controle de sessão não deve ficar duplicada nos handlers.
- Os handlers devem apenas coordenar entrada, saída e chamadas para serviços/casos de uso.
- Comentários e documentação devem ser escritos em português do Brasil.

## Critérios de Aceite

- `POST /whatsapp/messages/send-and-close` mantém o comportamento atual de `POST /notifications`.
- `GET /whatsapp/session/start` abre e mantém uma sessão ativa.
- `POST /whatsapp/messages/send` envia mensagem usando uma sessão já aberta.
- `GET /whatsapp/session/stop` encerra a sessão ativa.
- Erros de sessão aberta, sessão fechada, falha de abertura, falha de envio e falha de fechamento retornam mensagens personalizadas.
- Não há duplicação relevante de lógica entre os fluxos.
- A suíte de testes passa com 100% de cobertura.
- Nenhum teste acessa a página oficial do WhatsApp Web.
- A documentação está atualizada.
