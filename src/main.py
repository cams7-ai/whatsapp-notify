"""API REST do WhatsApp Notify."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from logging_config import configure_logging


def main() -> None:
    load_dotenv(Path.cwd() / ".env")
    configure_logging()
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("api.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
