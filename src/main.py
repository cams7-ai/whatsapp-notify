"""API REST do WhatsApp Notify."""

from __future__ import annotations

import os

import uvicorn

from logging_config import configure_logging


def main() -> None:
    configure_logging()
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
