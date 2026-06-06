"""Ponto de entrada da linha de comando do WhatsApp Notify."""

from __future__ import annotations

from app.config import ConfigError, load_config
from app.logger import configure_logger
from app.whatsapp_service import WhatsAppNotifyError, WhatsAppService


def main() -> int:
    logger = configure_logger()

    try:
        config = load_config()
        logger.info("Iniciando WhatsApp Notify")
        logger.info("Destino configurado: %s", config.target_name)
        logger.info("Perfil persistente: %s", config.profile_dir)

        service = WhatsAppService(config=config, logger=logger)
        service.run()

        logger.info("Aplicação finalizada com sucesso")
        return 0
    except ConfigError as exc:
        logger.error("Erro de configuração: %s", exc)
        return 2
    except WhatsAppNotifyError as exc:
        logger.error("Erro na automação do WhatsApp Web: %s", exc)
        return 1
    except Exception:
        logger.exception("Erro inesperado")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
