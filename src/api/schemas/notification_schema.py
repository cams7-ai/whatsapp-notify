from pydantic import BaseModel, ConfigDict, Field


class NotificationRequest(BaseModel):
    """Corpo opcional para sobrescrever destino e mensagem."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "contact": "Grupo Teste",
                    "message": "Mensagem enviada pela API",
                },
                {},
            ]
        },
    )

    target_name: str | None = Field(
        default=None,
        alias="contact",
        description="Nome exato do contato individual ou grupo.",
    )
    message: str | None = Field(
        default=None,
        description="Mensagem que será enviada pelo WhatsApp Web.",
    )


class SendAndCloseNotificationRequest(NotificationRequest):
    """Corpo opcional para o fluxo que pode abrir navegador."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "contact": "Grupo Teste",
                    "message": "Mensagem enviada pela API",
                    "headless": False,
                },
                {},
            ]
        },
    )

    headless: bool | None = Field(
        default=None,
        description="Sobrescreve WHATSAPP_HEADLESS neste envio, quando informado.",
    )


class NotificationResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "status": "enviado",
                    "message": "Mensagem enviada com sucesso.",
                    "contact": "Grupo Teste",
                    "elapsedTimeInSeconds": 12.345,
                }
            ]
        },
    )

    status: str
    message: str
    target_name: str = Field(alias="contact")
    elapsed_seconds: float = Field(
        alias="elapsedTimeInSeconds",
        description="Tempo total decorrido, em segundos, até confirmar o envio.",
    )


class SessionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "message": "Sessão do WhatsApp Web iniciada com sucesso.",
                }
            ]
        },
    )

    status: str
    message: str
