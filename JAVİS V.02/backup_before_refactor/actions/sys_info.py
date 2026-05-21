"""
Sistem bilgisi - Windows uyumlu psutil + yerel komutlar.
"""

from __future__ import annotations

import datetime
import socket
import subprocess

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def sys_info(query: str) -> str:
    query = (query or "all").lower().strip()
    results = []

    if query in ("battery", "pil", "all"):
        results.append(_battery())
    if query in ("cpu", "islemci", "işlemci", "all"):
        results.append(_cpu())
    if query in ("ram", "bellek", "memory", "all"):
        results.append(_ram())
    if query in ("disk", "depolama", "all"):
        results.append(_disk())
    if query in ("time", "saat", "zaman", "all"):
        now = datetime.datetime.now()
        results.append(f"Saat: {now.strftime('%H:%M:%S')}")
    if query in ("date", "tarih", "all"):
        now = datetime.datetime.now()
        results.append(f"Tarih: {now.strftime('%d.%m.%Y, %A')}")
    if query in ("network", "ag", "ağ", "wifi", "all"):
        results.append(_network())

    if not results:
        results.append(f"Bilinmeyen sorgu: {query}. battery/cpu/ram/disk/time/date/network/all kullanin.")

    return "\n".join(r for r in results if r)


def _battery() -> str:
    if HAS_PSUTIL:
        bat = psutil.sensors_battery()
        if bat:
            status = "Sarj oluyor" if bat.power_plugged else "Pilde"
            return f"Pil: %{bat.percent:.0f} - {status}"
        return "Pil bilgisi yok; cihaz masaustu olabilir."
    return "Pil bilgisi icin psutil gerekli."


def _cpu() -> str:
    if HAS_PSUTIL:
        usage = psutil.cpu_percent(interval=0.5)
        count = psutil.cpu_count(logical=True)
        freq = psutil.cpu_freq()
        freq_str = f", {freq.current:.0f} MHz" if freq else ""
        return f"CPU: %{usage:.1f} kullanim - {count} cekirdek{freq_str}"
    return "CPU bilgisi icin psutil gerekli."


def _ram() -> str:
    if HAS_PSUTIL:
        vm = psutil.virtual_memory()
        total = vm.total / (1024**3)
        used = vm.used / (1024**3)
        return f"RAM: {used:.1f}GB / {total:.1f}GB kullanimda (%{vm.percent:.0f})"
    return "RAM bilgisi icin psutil gerekli."


def _disk() -> str:
    if HAS_PSUTIL:
        du = psutil.disk_usage("C:\\")
        total = du.total / (1024**3)
        used = du.used / (1024**3)
        free = du.free / (1024**3)
        return f"Disk (C:): {used:.1f}GB kullanildi, {free:.1f}GB bos (toplam {total:.1f}GB)"
    return "Disk bilgisi icin psutil gerekli."


def _network() -> str:
    ssid = _wifi_ssid()
    ips: list[str] = []
    if HAS_PSUTIL:
        for entries in psutil.net_if_addrs().values():
            for entry in entries:
                if entry.family == socket.AF_INET and not entry.address.startswith("127."):
                    ips.append(entry.address)
    if ssid:
        return f"WiFi: {ssid} bagli" + (f" - IP {ips[0]}" if ips else "")
    if ips:
        return f"Ag: IP {ips[0]}"
    return "Ag baglantisi bulunamadi."


def _wifi_ssid() -> str:
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            text=True,
            timeout=5,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return ""

    for line in out.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("ssid") and "bssid" not in lower and ":" in stripped:
            return stripped.split(":", 1)[1].strip()
    return ""
