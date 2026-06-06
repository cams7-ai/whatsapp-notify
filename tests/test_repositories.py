import pytest
from types import SimpleNamespace
from pathlib import Path
import logging

from app.repositories import PlaywrightNotificationRepository
from app.config import AppConfig
from app import repositories
from app import domain


def test_playwright_repository_maps_authentication_error(monkeypatch, tmp_path):
    # Arrange
    cfg = AppConfig(
        target_name="T",
        message="M",
        headless=True,
        profile_dir=tmp_path,
        timeout_seconds=1,
    )
    logger = logging.getLogger("test")

    # Monkeypatch WhatsAppService and exception names in app.whatsapp_service
    import app.whatsapp_service as ws_mod

    class DummyAuthExc(Exception):
        pass

    class DummyService2:
        def __init__(self, config, logger):
            self.config = config
            self.logger = logger

        def run(self):
            raise ws_mod.AuthenticationTimeoutError("timeout")

    monkeypatch.setattr(ws_mod, 'WhatsAppService', DummyService2)
    monkeypatch.setattr(ws_mod, 'AuthenticationTimeoutError', DummyAuthExc)

    # Also ensure repository imports pick up when called
    repo = PlaywrightNotificationRepository(config=cfg, logger=logger)

    # Act / Assert
    with pytest.raises(domain.AuthenticationError):
        repo.send("target", "message")


def test_playwright_repository_maps_target_not_found(monkeypatch, tmp_path):
    class Service2:
        def __init__(self, config, logger):
            pass

        def run(self):
            raise ws_mod.TargetNotFoundError("not found")

    cfg = AppConfig(
        target_name="T",
        message="M",
        headless=False,
        profile_dir=tmp_path,
        timeout_seconds=1,
    )
    logger = logging.getLogger("test")

    import app.whatsapp_service as ws_mod

    monkeypatch.setattr(ws_mod, 'WhatsAppService', Service2)
    monkeypatch.setattr(ws_mod, 'TargetNotFoundError', Exception)

    repo = PlaywrightNotificationRepository(config=cfg, logger=logger)

    with pytest.raises(domain.TargetNotFoundError):
        repo.send("x", "y")


