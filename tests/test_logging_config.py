import logging

from logging_config import configure_logging


def test_configure_logging_uses_log_level_from_environment(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    configure_logging()

    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_defaults_to_info_for_invalid_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "INVALID")

    configure_logging()

    assert logging.getLogger().level == logging.INFO
