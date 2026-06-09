"""Metadados OpenAPI expostos pela camada HTTP."""

from __future__ import annotations

OPENAPI_TAGS = [
    {
        "name": "whatsapp",
        "description": (
            "Controle de sessão e envio de mensagens pelo WhatsApp Web usando "
            "dados da requisição ou variáveis de ambiente como fallback."
        ),
    },
]

BAD_REQUEST_EXAMPLES = {
    "invalidRequest": {
        "summary": "Corpo inválido",
        "value": {
            "error": {
                "code": "REQUISICAO_INVALIDA",
                "message": (
                    "Corpo da requisição inválido. Envie um JSON com os campos "
                    "opcionais esperados para este endpoint. O campo 'headless' é "
                    "aceito apenas em /whatsapp/session/start e "
                    "/whatsapp/messages/send-and-close."
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
                    "Informe 'contact' no corpo da requisição ou configure "
                    "WHATSAPP_TARGET_NAME no ambiente"
                ),
                "fields": ["contact"],
            }
        },
    },
    "contactNotFound": {
        "summary": "Contato ou grupo não encontrado",
        "value": {
            "error": {
                "code": "DESTINO_NAO_ENCONTRADO",
                "message": "Contato ou grupo não encontrado: Grupo Teste",
                "fields": ["contact"],
            }
        },
    },
    "sessionAlreadyOpen": {
        "summary": "Sessão já aberta",
        "value": {
            "error": {
                "code": "SESSAO_JA_ABERTA",
                "message": "Já existe uma sessão do WhatsApp Web aberta.",
            }
        },
    },
    "sessionClosed": {
        "summary": "Sessão fechada",
        "value": {
            "error": {
                "code": "SESSAO_FECHADA",
                "message": "A sessão do WhatsApp Web está fechada. Inicie a sessão antes de enviar mensagens.",
            }
        },
    },
}

INTERNAL_SERVER_ERROR_EXAMPLES = {
    "invalidConfiguration": {
        "summary": "Configuração inválida",
        "value": {
            "error": {
                "code": "CONFIGURACAO_INVALIDA",
                "message": (
                    "Configuração inválida do servidor: Valor inválido para "
                    "WHATSAPP_TIMEOUT_SECONDS: informe um número inteiro"
                ),
            }
        },
    },
    "authenticationExpired": {
        "summary": "Timeout de autenticação",
        "value": {
            "error": {
                "code": "AUTENTICACAO_EXPIRADA",
                "message": (
                    "Autenticação não concluída em 60 segundos. Escaneie o QR Code "
                    "do WhatsApp Web no navegador aberto e tente novamente."
                ),
            }
        },
    },
    "sessionStartFailure": {
        "summary": "Falha ao iniciar sessão",
        "value": {
            "error": {
                "code": "FALHA_AO_INICIAR_SESSAO",
                "message": "Não foi possível abrir a sessão do WhatsApp Web.",
            }
        },
    },
    "sessionStopFailure": {
        "summary": "Falha ao encerrar sessão",
        "value": {
            "error": {
                "code": "FALHA_AO_ENCERRAR_SESSAO",
                "message": "Não foi possível fechar a sessão do WhatsApp Web.",
            }
        },
    },
    "sendFailure": {
        "summary": "Falha no envio",
        "value": {
            "error": {
                "code": "FALHA_NO_ENVIO",
                "message": (
                    "Não foi possível confirmar o envio da mensagem: Mensagem não "
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
                "message": "Erro inesperado ao processar a requisição.",
            }
        },
    },
}
