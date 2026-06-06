# WhatsApp Notify

CLI em Python 3.12 para enviar mensagens pelo WhatsApp Web usando Playwright.

O projeto usa um perfil persistente do Chromium para reutilizar a sessão autenticada. Na primeira execução, ou quando a sessão expirar, será necessário escanear o QR Code do WhatsApp Web.

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

### Instalar os navegadores do Playwright

```powershell
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
```

Variáveis:

- `WHATSAPP_TARGET_NAME`: nome exato do contato individual ou grupo.
- `WHATSAPP_MESSAGE`: mensagem que será enviada.
- `WHATSAPP_HEADLESS`: use `false` para abrir o navegador visível, recomendado no Windows.
- `WHATSAPP_PROFILE_DIR`: diretório do perfil persistente do Chromium.
- `WHATSAPP_TIMEOUT_SECONDS`: tempo máximo para autenticação, busca e envio.

## Execução

```powershell
python -m app.main
```

Também é possível usar o comando instalado:

```powershell
whatsapp-notify
```

## Observações

- Na primeira execução será necessário escanear o QR Code.
- As sessões serão reutilizadas automaticamente pelo perfil persistente.
- Não apague o diretório definido em `WHATSAPP_PROFILE_DIR` se quiser manter a sessão.
- Mudanças na interface do WhatsApp Web podem exigir atualização dos seletores do Playwright em `src/app/whatsapp_service.py`.
- A automação usa WhatsApp Web diretamente no navegador; não usa bibliotecas não oficiais baseadas em engenharia reversa do WhatsApp.

## Tratamento de Erros

A aplicação registra no console erros de configuração, timeout de autenticação, contato ou grupo não encontrado e falha no envio.

Códigos de saída:

- `0`: execução concluída com sucesso.
- `1`: erro de automação ou erro inesperado.
- `2`: erro de configuração.
