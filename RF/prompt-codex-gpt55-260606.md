# Prompt para GPT-5.5 + Codex (PyCharm 2026.1.2)

Você é um agente de desenvolvimento de "software" executando no PyCharm 2026.1.2 com o plugin JetBrains AI, utilizando o agente Codex e o modelo GPT-5.5.

## Objetivo

Crie uma aplicação CLI em Python 3.12 chamada `WhatsApp Notify`.

A aplicação deve enviar mensagens pelo WhatsApp Web utilizando Playwright, permitindo envio para um contato individual ou para um grupo.

---

# Requisitos Técnicos

- Linguagem: Python 3.12
- Execução: Windows local
- Interface: CLI
- Automação: Playwright + WhatsApp Web
- Configuração via arquivo `.env`
- Nome do projeto: `WhatsApp Notify`
- Utilizar sessão persistente do navegador
- Evitar necessidade de escanear QR Code a cada execução
- Solicitar QR Code apenas na primeira execução ou quando a sessão expirar
- Não utilizar bibliotecas não oficiais baseadas em engenharia reversa do WhatsApp

---

# Estrutura Obrigatória

```text
whatsapp-notify/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── logger.py
│   └── whatsapp_service.py
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

# Arquivo .env.example

```env
WHATSAPP_TARGET_NAME=Nome do contato ou grupo
WHATSAPP_MESSAGE=Mensagem de teste enviada automaticamente
WHATSAPP_HEADLESS=false
WHATSAPP_PROFILE_DIR=.whatsapp-profile
WHATSAPP_TIMEOUT_SECONDS=60
```

---

# Funcionalidades Obrigatórias

1. Carregar configurações do `.env`.
2. Inicializar Playwright com perfil persistente.
3. Abrir https://web.whatsapp.com.
4. Verificar se o WhatsApp Web está autenticado.
5. Caso não esteja autenticado, aguardar leitura do QR Code.
6. Buscar contato ou grupo pelo nome informado em `WHATSAPP_TARGET_NAME`.
7. Abrir a conversa encontrada.
8. Digitar e enviar a mensagem definida em `WHATSAPP_MESSAGE`.
9. Exibir logs claros no console.
10. Finalizar a aplicação com código de sucesso ou erro.
11. Tratar erros como:
    - contato/grupo não encontrado
    - timeout de autenticação
    - falha ao enviar mensagem
    - variáveis obrigatórias ausentes

---

# Critérios de Implementação

- Utilizar:
  - playwright
  - python-dotenv
- Criar código modular, limpo e organizado.
- Evitar hardcode de mensagens, nomes e caminhos.
- Utilizar pathlib para manipulação de caminhos.
- Utilizar logging nativo do Python.
- Criar exceções ou mensagens de erro claras.
- O navegador deve abrir em modo visível por padrão no Windows.
- O projeto deve ser executável com:

```bash
python -m main
```

---

# README.md

O README deverá conter:

## Instalação

### Criar ambiente virtual

```powershell
python -m venv .venv
```

### Ativar ambiente

```powershell
.venv\Scripts\Activate.ps1
```

### Instalar dependências

```powershell
pip install -e .
```

### Instalar browsers do Playwright

```powershell
playwright install chromium
```

---

## Configuração

Criar arquivo `.env` com base em `.env.example`.

Exemplo:

```env
WHATSAPP_TARGET_NAME=Grupo Teste
WHATSAPP_MESSAGE=Mensagem enviada automaticamente
WHATSAPP_HEADLESS=false
WHATSAPP_PROFILE_DIR=.whatsapp-profile
WHATSAPP_TIMEOUT_SECONDS=60
```

---

## Execução

```powershell
python -m main
```

---

## Observações

- Na primeira execução será necessário escanear o QR Code.
- As sessões serão reutilizadas automaticamente.
- Mudanças na interface do WhatsApp Web podem exigir atualização dos seletores do Playwright.

---

# Critérios de Aceite

- Projeto instala sem erros.
- Código segue boas práticas Python.
- Estrutura modular e extensível.
- Logs claros e rastreáveis.
- Reutilização da sessão autenticada.
- Funciona para contato individual e grupo.
- Tratamento adequado de exceções.
- README completo.
- Código pronto para execução local no Windows.

---

# Processo de Entrega

Antes de gerar código:

1. Analise os requisitos.
2. Apresente a arquitetura proposta.
3. Identifique riscos e limitações.
4. Liste dependências.
5. Somente após isso implemente todos os arquivos do projeto.

A implementação deve ser completa e pronta para execução.