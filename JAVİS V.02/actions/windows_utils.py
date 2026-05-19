"""
Windows helpers for JARVIS actions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.parse
import webbrowser
from pathlib import Path


START_APP_IDS = {
    "whatsapp": "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
}


def open_url(url: str) -> bool:
    if not url:
        return False
    try:
        os.startfile(url)  # type: ignore[attr-defined]
        return True
    except Exception:
        return webbrowser.open(url)


def copy_to_clipboard(text: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(text)
        return
    except Exception:
        pass

    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
        input=text,
        text=True,
        capture_output=True,
        timeout=5,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Clipboard failed").strip())


def press_enter(delay: float = 0.0) -> tuple[bool, str]:
    if delay > 0:
        time.sleep(delay)
    try:
        import pyautogui

        pyautogui.press("enter")
        return True, "ok"
    except Exception as exc:
        return False, f"Enter tusu gonderilemedi: {exc}"


def hotkey(*keys: str, delay: float = 0.0) -> tuple[bool, str]:
    if delay > 0:
        time.sleep(delay)
    try:
        import pyautogui

        pyautogui.hotkey(*keys)
        return True, "ok"
    except Exception as exc:
        return False, f"Klavye kisayolu gonderilemedi: {exc}"


def write_text(text: str, delay: float = 0.0) -> tuple[bool, str]:
    if delay > 0:
        time.sleep(delay)
    try:
        import pyautogui

        pyautogui.write(text, interval=0.01)
        return True, "ok"
    except Exception as exc:
        return False, f"Yazi yazilamadi: {exc}"


def send_media_key(action: str, delay: float = 0.0) -> tuple[bool, str]:
    if delay > 0:
        time.sleep(delay)

    keys = {
        "play_pause": 0xB3,
        "pause": 0xB3,
        "resume": 0xB3,
        "stop": 0xB2,
        "next": 0xB0,
        "previous": 0xB1,
        "mute": 0xAD,
        "volume_up": 0xAF,
        "volume_down": 0xAE,
    }
    vk = keys.get((action or "").strip().lower())
    if not vk:
        return False, f"Bilinmeyen medya komutu: {action}"

    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        return True, "ok"
    except Exception:
        try:
            import pyautogui

            fallback_keys = {
                "play_pause": "playpause",
                "pause": "playpause",
                "resume": "playpause",
                "stop": "stop",
                "next": "nexttrack",
                "previous": "prevtrack",
                "mute": "volumemute",
                "volume_up": "volumeup",
                "volume_down": "volumedown",
            }
            pyautogui.press(fallback_keys[action])
            return True, "ok"
        except Exception as exc:
            return False, f"Medya tusu gonderilemedi: {exc}"


def sleep_windows() -> tuple[bool, str]:
    try:
        import ctypes

        ctypes.windll.PowrProf.SetSuspendState(False, True, False)
        return True, "Windows uyku moduna geciyor."
    except Exception:
        try:
            subprocess.Popen(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, "Windows uyku moduna geciyor."
        except Exception as exc:
            return False, f"Uyku modu baslatilamadi: {exc}"


def click_active_window(x_from_right: int, y_from_top: int, delay: float = 0.0) -> tuple[bool, str]:
    if delay > 0:
        time.sleep(delay)
    try:
        import ctypes
        import pyautogui
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        x = max(rect.left, rect.right - x_from_right)
        y = rect.top + y_from_top
        pyautogui.click(x, y)
        return True, "ok"
    except Exception as exc:
        return False, f"Tiklama yapilamadi: {exc}"


def _candidate_executables(app_name: str) -> list[str]:
    normalized = app_name.lower().strip()
    aliases = {
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "firefox": "firefox.exe",
        "spotify": "spotify.exe",
        "whatsapp": "WhatsApp.exe",
        "telegram": "Telegram.exe",
        "discord": "Discord.exe",
        "notion": "Notion.exe",
        "slack": "slack.exe",
        "vscode": "Code.exe",
        "vs code": "Code.exe",
        "visual studio code": "Code.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "powershell": "powershell.exe",
        "cmd": "cmd.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "calculator": "calc.exe",
        "hesap makinesi": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "settings": "ms-settings:",
        "ayarlar": "ms-settings:",
        "calendar": "outlookcal:",
        "takvim": "outlookcal:",
        "mail": "outlookmail:",
    }
    executable = aliases.get(normalized, app_name)
    candidates = [executable]
    if not executable.lower().endswith((".exe", ":")):
        candidates.append(f"{executable}.exe")
    return candidates


def open_app(app_name: str) -> tuple[bool, str]:
    if not app_name:
        return False, "Uygulama adi belirtilmedi."

    normalized = app_name.lower().strip()
    app_id = START_APP_IDS.get(normalized)
    if app_id:
        try:
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, app_name
        except Exception:
            pass

    for candidate in _candidate_executables(app_name):
        if candidate.endswith(":"):
            if open_url(candidate):
                return True, app_name
            continue

        found = shutil.which(candidate)
        try:
            if found:
                subprocess.Popen([found], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, candidate
            os.startfile(candidate)  # type: ignore[attr-defined]
            return True, candidate
        except Exception:
            continue

    query = urllib.parse.quote(app_name)
    if open_url(f"https://www.microsoft.com/search?q={query}"):
        return False, f"'{app_name}' bulunamadi; Microsoft aramasi acildi."
    return False, f"'{app_name}' bulunamadi veya acilamadi."


def app_exists(app_name: str) -> bool:
    return any(shutil.which(candidate) for candidate in _candidate_executables(app_name))


def active_window_screenshot(output_path: Path) -> dict:
    try:
        import pyautogui
    except Exception as exc:
        return {"ok": False, "error": "pyautogui_missing", "detail": f"pyautogui yuklu degil: {exc}"}

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        width, height = max(1, right - left), max(1, bottom - top)
        image = pyautogui.screenshot(region=(left, top, width, height))
        image.save(output_path)

        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        return {
            "ok": True,
            "image_path": str(output_path),
            "owner_name": "",
            "window_title": title_buf.value,
            "bounds": {"x": left, "y": top, "width": width, "height": height},
            "detail": "active_window",
        }
    except Exception:
        try:
            image = pyautogui.screenshot()
            image.save(output_path)
            return {
                "ok": True,
                "image_path": str(output_path),
                "owner_name": "Windows",
                "window_title": "Ekran",
                "bounds": {},
                "detail": "fullscreen",
            }
        except Exception as exc:
            return {"ok": False, "error": "capture_failed", "detail": str(exc)}


def full_screen_screenshot(output_path: Path) -> dict:
    try:
        import pyautogui
    except Exception as exc:
        return {"ok": False, "error": "pyautogui_missing", "detail": f"pyautogui yuklu degil: {exc}"}

    try:
        image = pyautogui.screenshot()
        image.save(output_path)
        width, height = image.size
        return {
            "ok": True,
            "image_path": str(output_path),
            "owner_name": "Windows",
            "window_title": "Tum ekran",
            "bounds": {"x": 0, "y": 0, "width": width, "height": height},
            "detail": "full_screen",
        }
    except Exception as exc:
        return {"ok": False, "error": "capture_failed", "detail": str(exc)}
