"""The one place API keys are read and stored (BYOK). Adapters get their key from here, through
their constructor, and never read the environment or the keychain themselves.

Sources, in order: the OS keychain (via `keyring`; the macOS Keychain on a Mac), then settings
(environment variables or the gitignored .env). Keys are never written to the database, files or
logs. Errors from the keychain are reported by type only, never by message.
"""

import logging
import re

import keyring
from keyring.errors import KeyringError, PasswordDeleteError
from pydantic import SecretStr

from adaptive_rag.config import Settings

CLOUD_PROVIDERS = ("openai", "gemini", "anthropic")
KEYCHAIN_SERVICE = "adaptive-rag"
MAX_KEY_CHARS = 512
# Printable ASCII without spaces: every provider's key format fits, and nothing can break a header.
_KEY_PATTERN = re.compile(r"[\x21-\x7e]+")

logger = logging.getLogger(__name__)


class KeychainError(Exception):
    """The keychain couldn't be read or written. The message never contains a key."""


class InvalidKey(ValueError):
    """The submitted key has the wrong shape. The message never contains the key."""


def _check_provider(provider: str) -> None:
    if provider not in CLOUD_PROVIDERS:
        raise ValueError(f"unknown cloud provider: {provider}")


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _from_keychain(provider: str) -> str | None:
    try:
        return _clean(keyring.get_password(KEYCHAIN_SERVICE, provider))
    except KeyringError as exc:
        # Fall back to .env so a locked or missing keychain doesn't block configured keys.
        logger.warning("Keychain read failed for %s (%s)", provider, type(exc).__name__)
        return None


def _from_settings(settings: Settings, provider: str) -> str | None:
    key = getattr(settings, f"{provider}_api_key")
    return _clean(key.get_secret_value()) if key is not None else None


def api_key(settings: Settings, provider: str) -> SecretStr | None:
    """The key for a cloud provider (keychain first, then settings), or None if neither has one."""
    _check_provider(provider)
    key = _from_keychain(provider) or _from_settings(settings, provider)
    return SecretStr(key) if key else None


def key_source(settings: Settings, provider: str) -> str:
    """Where the key comes from: "keychain", "env" or "not set". Never the key itself."""
    _check_provider(provider)
    if _from_keychain(provider):
        return "keychain"
    return "env" if _from_settings(settings, provider) else "not set"


def store_key(provider: str, key: str) -> None:
    _check_provider(provider)
    key = key.strip()
    if not key or len(key) > MAX_KEY_CHARS or not _KEY_PATTERN.fullmatch(key):
        raise InvalidKey(f"A key must be 1 to {MAX_KEY_CHARS} printable characters with no spaces.")
    try:
        keyring.set_password(KEYCHAIN_SERVICE, provider, key)
    except KeyringError as exc:
        logger.warning("Keychain write failed for %s (%s)", provider, type(exc).__name__)
        raise KeychainError("The key couldn't be saved to the system keychain.") from None


def remove_key(provider: str) -> None:
    """Remove the keychain key. A missing key is not an error. Keys in .env are not touched."""
    _check_provider(provider)
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, provider)
    except PasswordDeleteError:
        pass
    except KeyringError as exc:
        logger.warning("Keychain delete failed for %s (%s)", provider, type(exc).__name__)
        raise KeychainError("The key couldn't be removed from the system keychain.") from None
