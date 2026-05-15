"""Lambda handler that runs Alembic migrations from inside the VPC.

Invoked by the GitHub Actions deploy workflow after `terraform apply`:
    aws lambda invoke --function-name stocktopus-<env>-migrate ...

The function uses the same container image as the main app Lambda but with
a different CMD override (`stocktopus.db.migrations.lambda_migrate.handler`).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Run `alembic upgrade head` against the Aurora cluster via RDS Proxy."""
    logger.info("Migration Lambda invoked")
    try:
        db_url = _build_db_url()
        _run_alembic(db_url)
        logger.info("Alembic migrations complete")
        return {"status": "ok"}
    except Exception:
        logger.exception("Migration failed")
        raise


def _build_db_url() -> str:
    """Construct the asyncpg DATABASE_URL, fetching the password from Secrets Manager."""
    secret_arn = os.environ.get("DB_SECRET_ARN", "")
    proxy_endpoint = os.environ.get("RDS_PROXY_ENDPOINT", "")
    db_name = os.environ.get("DB_NAME", "stocktopus")

    if secret_arn and proxy_endpoint:
        import boto3

        client = boto3.client("secretsmanager")
        secret = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])
        username = secret["username"]
        password = urllib.parse.quote_plus(secret["password"])
        return f"postgresql+asyncpg://{username}:{password}@{proxy_endpoint}:5432/{db_name}"

    # Fall back to DATABASE_URL (local dev / CI with public DB)
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("No database credentials configured — set DB_SECRET_ARN or DATABASE_URL")
    return url


def _run_alembic(db_url: str) -> None:
    """Run Alembic migrations programmatically without an alembic.ini file."""
    # env.py reads DATABASE_URL from os.environ at script load time, so set it
    # here before importing alembic command (which will execute env.py).
    # Using set_main_option("sqlalchemy.url", ...) does NOT work because env.py
    # bypasses it, and configparser chokes on %-encoded characters in passwords.
    os.environ["DATABASE_URL"] = db_url

    from alembic import command
    from alembic.config import Config

    cfg = Config()
    # In the Lambda container, source is at /var/task (pip install --target .)
    cfg.set_main_option("script_location", "/var/task/stocktopus/db/migrations")
    command.upgrade(cfg, "head")
