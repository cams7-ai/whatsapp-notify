from pydantic import BaseModel, ConfigDict

class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[str] | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "DADOS_OBRIGATORIOS_AUSENTES",
                        "message": (
                            "Informe 'contact' no corpo da requisição ou configure "
                            "WHATSAPP_TARGET_NAME no ambiente"
                        ),
                        "fields": ["contact"],
                    }
                }
            ]
        }
    )

    error: ErrorDetail