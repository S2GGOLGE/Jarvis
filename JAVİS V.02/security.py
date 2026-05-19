from __future__ import annotations

import hashlib
import hmac

from app_config import get_app_config_value, save_app_config


OWNER_PIN_KEY = "owner_pin_hash"


def _hash_pin(pin: str) -> str:
    normalized = str(pin or "").strip()
    if len(normalized) < 4:
        raise ValueError("Owner PIN en az 4 karakter olmali.")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def set_owner_pin(pin: str) -> None:
    save_app_config({OWNER_PIN_KEY: _hash_pin(pin)})


def has_owner_pin() -> bool:
    return bool(str(get_app_config_value(OWNER_PIN_KEY, "") or "").strip())


def verify_owner_pin(pin: str) -> bool:
    expected = str(get_app_config_value(OWNER_PIN_KEY, "") or "").strip()
    if not expected:
        return False
    try:
        actual = _hash_pin(pin)
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)
