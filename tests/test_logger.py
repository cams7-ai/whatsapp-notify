from app.logger import configure_logger


def test_configure_logger():
    logger = configure_logger()
    assert logger.name == "whatsapp_notify"
    assert logger.level == 20  # INFO
    # calling again should return same logger without adding handlers
    logger2 = configure_logger()
    assert logger is logger2

