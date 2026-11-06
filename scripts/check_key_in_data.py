"""Check whether any configured API key appears in a file under the data directory.

Security finding of 2026-11-06 (PROGRESS.md): indexes built before the fix could contain key
bytes. Prints only provider names and file paths, never a key or any part of one.

Run from the repo root: python scripts/check_key_in_data.py
"""

from adaptive_rag.config import Settings
from adaptive_rag.providers.keys import CLOUD_PROVIDERS, api_key


def main() -> int:
    settings = Settings()
    keys = {}
    for provider in CLOUD_PROVIDERS:
        key = api_key(settings, provider)
        if key is not None and len(key.get_secret_value()) >= 8:
            keys[provider] = key.get_secret_value().encode()
    if not keys:
        print("No keys configured; nothing to check.")
        return 0
    found = 0
    for path in sorted(settings.data_dir.rglob("*")):
        if not path.is_file():
            continue
        content = path.read_bytes()
        for provider, key in keys.items():
            if key in content:
                found += 1
                print(f"{provider} key found in {path}")
    print(f"Checked {', '.join(keys)} keys under {settings.data_dir}/: {found} file match(es).")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
