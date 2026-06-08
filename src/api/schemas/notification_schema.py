from pydantic import BaseModel, ConfigDict, Field

class NotificationRequest(BaseModel):
    """Corpo opcional para sobrescrever o destino e a mensagem do ambiente."""

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
