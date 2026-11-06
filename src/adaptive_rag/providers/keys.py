"""The one place API keys are read (BYOK). Adapters get their key from here, through their
constructor, and never read the environment themselves.

Stage 6 reads keys from settings (environment variables or the gitignored .env). Stage 7 adds an
OS-keychain source here, without changing the adapters (PROGRESS.md decision 60).
"""

from pydantic import SecretStr

from adaptive_rag.config import Settings

CLOUD_PROVIDERS = ("openai", "gemini", "anthropic")


def api_key(settings: Settings, provider: str) -> SecretStr | None:
    """The configured key for a cloud provider, or None. An empty value counts as no key."""
    if provider not in CLOUD_PROVIDERS:
        raise ValueError(f"unknown cloud provider: {provider}")
    key = getattr(settings, f"{provider}_api_key")
    return key if key is not None and key.get_secret_value().strip() else None
