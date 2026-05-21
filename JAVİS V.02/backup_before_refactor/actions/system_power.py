from __future__ import annotations

import logging
import threading
import time

from actions.windows_utils import sleep_windows

LOG = logging.getLogger("jarvis.actions.system_power")
POWER_LOCK = threading.RLock()
MIN_REPEAT_SECONDS = 10
_last_power_action_at = 0.0


def system_sleep() -> str:
    global _last_power_action_at

    with POWER_LOCK:
        now = time.monotonic()
        if now - _last_power_action_at < MIN_REPEAT_SECONDS:
            return "Guvenlik: Uyku komutu zaten yeni gonderildi."

        ok, detail = sleep_windows()
        if ok:
            _last_power_action_at = now
            return detail or "Windows uyku moduna geciyor."

        LOG.warning("system_sleep_failed: %s", detail)
        return detail or "Uyku modu baslatilamadi."
