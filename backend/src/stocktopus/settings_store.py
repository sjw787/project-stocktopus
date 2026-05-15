"""Settings repository abstraction.

Provides a uniform interface for reading and writing editable runtime settings.
Implementations:
  - EnvSettingsRepository  — reads/writes a local .env file (development)
  - DynamoDBSettingsRepository — reads/writes an AWS DynamoDB table (Lambda / production)

Usage:
    from stocktopus.settings_store import get_settings_repository
    repo = get_settings_repository()
    value = await repo.get("llm_model")
    await repo.set("llm_model", "gpt-5-mini")
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SettingsRepository(ABC):
    """Abstract interface for editable runtime settings storage."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the current string value for *key*, or None if not set."""

    @abstractmethod
    async def set(self, key: str, value: str) -> None:
        """Persist *key* = *value*."""

    @abstractmethod
    async def get_all(self) -> dict[str, str]:
        """Return all editable settings as a flat {key: value} dict."""


# ── Local .env implementation ─────────────────────────────────────────────────


class EnvSettingsRepository(SettingsRepository):
    """Reads and writes editable settings from a local .env file."""

    def __init__(self, env_path: Path | None = None) -> None:
        self._path = env_path or Path(os.getenv("DOTENV_PATH", ".env"))

    async def get(self, key: str) -> str | None:
        pairs = self._read_pairs()
        return pairs.get(key.upper())

    async def set(self, key: str, value: str) -> None:
        _update_env_file(self._path, {key.upper(): value})

    async def get_all(self) -> dict[str, str]:
        return self._read_pairs()

    def _read_pairs(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        result: dict[str, str] = {}
        for line in self._path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, v = stripped.partition("=")
                result[k.strip().upper()] = v.strip()
        return result


# ── DynamoDB implementation ───────────────────────────────────────────────────

# DynamoDB table schema:
#   pk (S) = "settings"       — partition key shared by all editable settings
#   sk (S) = "<SETTING_KEY>"  — one item per setting (upper-cased)
#   value (S)                 — the string value
#
# Feature-flag items use a separate pk:
#   pk = "schedule", sk = "ingestion" | "paper"  → {"enabled": bool}

_SETTINGS_PK = "settings"


class DynamoDBSettingsRepository(SettingsRepository):
    """Reads and writes editable settings from a DynamoDB table."""

    def __init__(self, table_name: str) -> None:
        self._table_name = table_name

    # ── async wrappers around sync boto3 ──────────────────────────────────────

    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(self._sync_get, key.upper())

    async def set(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._sync_set, key.upper(), value)

    async def get_all(self) -> dict[str, str]:
        return await asyncio.to_thread(self._sync_get_all)

    # ── sync helpers (run in executor) ────────────────────────────────────────

    def _table(self) -> Any:
        import boto3

        ddb = boto3.resource("dynamodb")
        return ddb.Table(self._table_name)

    def _sync_get(self, key: str) -> str | None:
        resp = self._table().get_item(Key={"pk": _SETTINGS_PK, "sk": key})
        item = resp.get("Item")
        return item["value"] if item else None

    def _sync_set(self, key: str, value: str) -> None:
        self._table().put_item(Item={"pk": _SETTINGS_PK, "sk": key, "value": value})

    def _sync_get_all(self) -> dict[str, str]:
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(KeyConditionExpression=Key("pk").eq(_SETTINGS_PK))
        return {item["sk"]: item["value"] for item in resp.get("Items", [])}


# ── Schedule-flag helpers ─────────────────────────────────────────────────────


class ScheduleFlagsRepository:
    """Read/write schedule feature flags stored in DynamoDB.

    Items:  pk="schedule", sk="ingestion"|"paper", enabled=bool
    Falls back to True when not running in Lambda (no table configured).
    """

    def __init__(self, table_name: str | None = None) -> None:
        self._table_name = table_name or os.getenv("SETTINGS_TABLE_NAME", "")

    async def get_all(self) -> dict[str, bool]:
        if not self._table_name:
            return {"ingestion": True, "paper": True}
        return await asyncio.to_thread(self._sync_get_all)

    async def set(self, schedule_name: str, enabled: bool) -> None:
        if not self._table_name:
            raise RuntimeError("SETTINGS_TABLE_NAME is not configured")
        await asyncio.to_thread(self._sync_set, schedule_name, enabled)

    def _table(self) -> Any:
        import boto3

        ddb = boto3.resource("dynamodb")
        return ddb.Table(self._table_name)

    def _sync_get_all(self) -> dict[str, bool]:
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(KeyConditionExpression=Key("pk").eq("schedule"))
        return {item["sk"]: bool(item.get("enabled", True)) for item in resp.get("Items", [])}

    def _sync_set(self, schedule_name: str, enabled: bool) -> None:
        self._table().put_item(Item={"pk": "schedule", "sk": schedule_name, "enabled": enabled})


# ── Factory ───────────────────────────────────────────────────────────────────


def get_settings_repository() -> SettingsRepository:
    """Return the appropriate repository for the current runtime environment."""
    from stocktopus.config import get_settings

    settings = get_settings()
    if settings.lambda_runtime and settings.settings_table_name:
        return DynamoDBSettingsRepository(table_name=settings.settings_table_name)
    return EnvSettingsRepository()


# ── .env mutation helper (shared by EnvSettingsRepository) ───────────────────


def _update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Update or append key=value pairs in a .env file, preserving comments."""
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(updates)
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().upper()
            if key in remaining:
                new_lines.append(f"{key}={remaining.pop(key)}")
                continue
        new_lines.append(line)

    if remaining:
        new_lines.append("")
        for key, value in remaining.items():
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n")
