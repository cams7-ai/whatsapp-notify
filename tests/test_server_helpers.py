from types import SimpleNamespace

from api.server import _http_error_code_and_message, _validation_error_fields
from starlette import status


def test_http_error_code_and_message_various():
    exc404 = SimpleNamespace(status_code=status.HTTP_404_NOT_FOUND, detail="x")
    assert _http_error_code_and_message(exc404)[0] == "ROTA_NAO_ENCONTRADA"

    exc405 = SimpleNamespace(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="x")
    assert _http_error_code_and_message(exc405)[0] == "METODO_NAO_PERMITIDO"

    exc400 = SimpleNamespace(status_code=400, detail="Bad request")
    assert _http_error_code_and_message(exc400)[0] == "ERRO_NA_REQUISICAO"

    exc500 = SimpleNamespace(status_code=500, detail=None)
    assert _http_error_code_and_message(exc500)[0] == "ERRO_INTERNO"


def test_validation_error_fields():
    # Create a fake exception with errors() method
    class FakeValidationErr:
        def errors(self):
            return [
                {"loc": ("body", "message"), "msg": "error"},
                {"loc": ("body", 0, "field"), "msg": "err"},
            ]

    fields = _validation_error_fields(FakeValidationErr())
    assert set(fields) == {"message", "field"}

