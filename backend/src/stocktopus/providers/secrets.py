"""Secrets provider — abstracts credential retrieval to support future per-user vaults."""

import os
from abc import ABC, abstractmethod


class SecretsProvider(ABC):
    """Abstract provider for secret/credential retrieval.

    Implement this to support per-user secret vaults (HashiCorp Vault, AWS Secrets
    Manager, etc.) without touching any call site.
    """

    @abstractmethod
    def get(self, key: str) -> str:
        """Return the secret value for `key`. Raise KeyError if not found."""
        ...

    def get_or_default(self, key: str, default: str = "") -> str:
        """Return the secret or `default` if it doesn't exist."""
        try:
            return self.get(key)
        except KeyError:
            return default


class EnvSecretsProvider(SecretsProvider):
    """Reads secrets from environment variables — default for single-user mode."""

    def get(self, key: str) -> str:
        value = os.environ.get(key)
        if not value:
            raise KeyError(f"Secret '{key}' not set in environment")
        return value
