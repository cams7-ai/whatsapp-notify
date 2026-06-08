"""Metadados OpenAPI expostos pela camada HTTP."""

from __future__ import annotations

OPENAPI_TAGS = [
    {
        "name": "whatsapp",
        "description": (
            "Controle de sessao e envio de mensagens pelo WhatsApp Web usando "
            "dados da requisicao ou variaveis de ambiente como fallback."
        ),
    },
]

BAD_REQUEST_EXAMPLES = {
    "invalidRequest": {
        "summary": "Corpo invalido",
        "value": {
            "error": {
                "code": "REQUISICAO_INVALIDA",
                "message": (
                    "Corpo da requisicao invalido. Envie um JSON com os campos "
                    "opcionais 'contact' e 'message'."
                ),
                "fields": ["message"],
            }
        },
    },
    "missingRequiredValue": {
        "summary": "Campo efetivo ausente",
        "value": {
            "error": {
                "code": "DADOS_OBRIGATORIOS_AUSENTES",
                "message": (
                    "Informe 'contact' no corpo da requisicao ou configure "
                    "WHATSAPP_TARGET_NAME no ambiente"
                ),
                "fields": ["contact"],
            }
        },
    },
    "contactNotFound": {
        "summary": "Contato ou grupo nao encontrado",
        "value": {
            "error": {
                "code": "DESTINO_NAO_ENCONTRADO",
                "message": "Contato ou grupo nao encontrado: Grupo Teste",
                "fields": ["contact"],
            }
        },
    },
    "sessionAlreadyOpen": {
        "summary": "Sessao ja aberta",
        "value": {
            "error": {
                "code": "SESSAO_JA_ABERTA",
                "message": "Ja existe uma sessao do WhatsApp Web aberta.",
            }
        },
    },
    "sessionClosed": {
        "summary": "Sessao fechada",
        "value": {
            "error": {
                "code": "SESSAO_FECHADA",
                "message": "A sessao do WhatsApp Web esta fechada. Inicie a sessao antes de enviar mensagens.",
            }
        },
    },
}

INTERNAL_SERVER_ERROR_EXAMPLES = {
    "invalidConfiguration": {
        "summary": "Configuracao invalida",
        "value": {
            "error": {
                "code": "CONFIGURACAO_INVALIDA",
                "message": (
                    "Configuracao invalida do servidor: Valor invalido para "
                    "WHATSAPP_TIMEOUT_SECONDS: informe um numero inteiro"
                ),
            }
        },
    },
    "authenticationExpired": {
        "summary": "Timeout de autenticacao",
        "value": {
            "error": {
                "code": "AUTENTICACAO_EXPIRADA",
                "message": (
                    "Autenticacao nao concluida em 60 segundos. Escaneie o QR Code "
                    "do WhatsApp Web no navegador aberto e tente novamente."
                ),
            }
        },
    },
    "sessionStartFailure": {
        "summary": "Falha ao iniciar sessao",
        "value": {
            "error": {
                "code": "FALHA_AO_INICIAR_SESSAO",
                "message": "Nao foi possivel abrir a sessao do WhatsApp Web.",
            }
        },
    },
    "sessionStopFailure": {
        "summary": "Falha ao encerrar sessao",
        "value": {
            "error": {
                "code": "FALHA_AO_ENCERRAR_SESSAO",
                "message": "Nao foi possivel fechar a sessao do WhatsApp Web.",
            }
        },
    },
    "sendFailure": {
        "summary": "Falha no envio",
        "value": {
            "error": {
                "code": "FALHA_NO_ENVIO",
                "message": (
                    "Nao foi possivel confirmar o envio da mensagem: Mensagem nao "
                    "foi confirmada pelo WhatsApp Web. Status detectado: pendente."
                ),
            }
        },
    },
    "internalError": {
        "summary": "Erro inesperado",
        "value": {
            "error": {
                "code": "ERRO_INTERNO",
                "message": "Erro inesperado ao processar a requisicao.",
            }
        },
    },
}
