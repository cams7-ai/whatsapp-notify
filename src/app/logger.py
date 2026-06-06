"""Configuração dos logs exibidos no console."""

from __future__ import annotations

import logging
import sys


def configure_logger() -> logging.Logger:
    logger = logging.getLogger("whatsapp_notify")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    return logger
