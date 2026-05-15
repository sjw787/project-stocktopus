import sys

from loguru import logger

from stocktopus.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    logger.remove()

    if settings.env in ("production", "staging"):
        logger.add(
            sys.stdout,
            format="{time} {level} {message}",
            serialize=True,
            level="INFO",
        )
    else:
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
                "<level>{message}</level>"
            ),
            level="DEBUG",
            colorize=True,
        )

    # Skip file logging in Lambda (read-only filesystem); CloudWatch captures stdout.
    import os

    if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        logger.add(
            "logs/stocktopus.log",
            rotation="1 day",
            retention="30 days",
            compression="gz",
            level="INFO",
            serialize=True,
        )
