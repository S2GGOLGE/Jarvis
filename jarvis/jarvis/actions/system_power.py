from __future__ import annotations

from actions.windows_utils import sleep_windows


def system_sleep() -> str:
    ok, detail = sleep_windows()
    return detail if ok else detail
