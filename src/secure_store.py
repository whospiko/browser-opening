from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app_log import get_logger
from paths import APP_NAME, profiles_dir

KEYRING_SERVICE = APP_NAME
KEYRING_USERNAME = "config-key"
ENVELOPE_VERSION = 1


class ConfigSecurityError(Exception):
    """Raised when encrypted config cannot be decrypted or the key is missing."""


def _fallback_key_path() -> Path:
    return profiles_dir() / "config.key"


def _read_fallback_key() -> bytes | None:
    path = _fallback_key_path()
    if not path.is_file():
        return None
    raw = path.read_bytes().strip()
    return raw or None


def _write_fallback_key(key: bytes) -> None:
    path = _fallback_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _keyring_get() -> bytes | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None
    if not value:
        return None
    return value.encode("utf-8")


def _keyring_set(key: bytes) -> bool:
    try:
        import keyring
    except ImportError:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key.decode("utf-8"))
        return True
    except Exception:
        return False


def get_or_create_key() -> bytes:
    """Return the Fernet key from the OS keyring, or create and store one."""
    log = get_logger()
    existing = _keyring_get()
    if existing:
        log.info("Config key source: keyring")
        return existing

    existing = _read_fallback_key()
    if existing:
        # Prefer promoting a fallback key into the keyring when available.
        promoted = _keyring_set(existing)
        log.info(
            "Config key source: fallback-file%s",
            " (promoted to keyring)" if promoted else "",
        )
        return existing

    key = Fernet.generate_key()
    if _keyring_set(key):
        log.info("Config key source: created-in-keyring")
    else:
        _write_fallback_key(key)
        log.info("Config key source: created-in-fallback-file")
    return key


def load_key() -> bytes:
    """Load an existing key; raise if none is available (needed to decrypt)."""
    log = get_logger()
    existing = _keyring_get()
    if existing:
        log.info("Config key source: keyring")
        return existing
    existing = _read_fallback_key()
    if existing:
        log.info("Config key source: fallback-file")
        return existing
    log.error("Config key source: missing")
    raise ConfigSecurityError(
        "Encrypted config found, but no decryption key is available for this user. "
        "Open the Config app on this machine (same user account) and Save again, "
        "or restore the key from the OS credential store / config.key backup."
    )


def is_encrypted_envelope(data: dict[str, Any]) -> bool:
    return bool(data.get("encrypted")) and "data" in data


def encrypt_payload(plaintext: dict[str, Any]) -> dict[str, Any]:
    key = get_or_create_key()
    token = Fernet(key).encrypt(
        json.dumps(plaintext, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return {
        "encrypted": True,
        "version": ENVELOPE_VERSION,
        "data": token.decode("utf-8"),
    }


def decrypt_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    log = get_logger()
    version = envelope.get("version", ENVELOPE_VERSION)
    if version != ENVELOPE_VERSION:
        raise ConfigSecurityError(
            f"Unsupported encrypted config version: {version}."
        )
    raw = envelope.get("data")
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigSecurityError("Encrypted config is missing ciphertext.")

    key = load_key()
    try:
        plain = Fernet(key).decrypt(raw.encode("utf-8"))
    except InvalidToken as exc:
        log.error("Config decrypt failed: key does not match file")
        raise ConfigSecurityError(
            "Could not decrypt config.json. The key does not match this file "
            "(wrong user/machine, or a different key). Run Config and Save again "
            "on this account, or restore the matching key."
        ) from exc

    try:
        data = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigSecurityError("Decrypted config is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ConfigSecurityError("Decrypted config must be a JSON object.")
    log.info("Config decrypted successfully")
    return data
