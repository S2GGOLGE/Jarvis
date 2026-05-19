"""
Medya oynatma - Windows icin YouTube ve Spotify destekli.
"""

from __future__ import annotations

import time
import urllib.parse

from actions.browser import browser_control
from actions.windows_utils import app_exists, open_url, press_enter, send_media_key


def _play_youtube(query: str) -> str:
    return browser_control("play_youtube", query=query)


def _play_spotify(query: str, autoplay: bool = True) -> str:
    encoded_query = urllib.parse.quote(query.strip())
    search_url = f"spotify:search:{encoded_query}"

    if not app_exists("spotify"):
        web_url = f"https://open.spotify.com/search/{encoded_query}"
        open_url(web_url)
        return f"Spotify Desktop bulunamadi; Spotify Web aramasi acildi: {query}"

    if not open_url(search_url):
        return "Spotify acilamadi."

    if not autoplay:
        return f"Spotify icinde '{query}' aramasi acildi."

    time.sleep(2.0)
    ok, detail = press_enter()
    if ok:
        time.sleep(0.7)
        press_enter()
        return f"Spotify'da arama acildi ve ilk sonuc oynatilmaya calisildi: {query}"
    return f"Spotify aramasi acildi ama otomatik oynatma tamamlanamadi: {detail}"


def _play_apple_music(query: str, autoplay: bool = True) -> str:
    encoded_query = urllib.parse.quote(query.strip())
    url = f"https://music.apple.com/search?term={encoded_query}"
    open_url(url)
    return f"Apple Music Windows/Web aramasi acildi: {query}"


def play_media(query: str, provider: str = "auto", autoplay: bool = True) -> str:
    if not query or not query.strip():
        return "Calinacak icerik belirtilmedi."

    normalized_provider = (provider or "auto").strip().lower()
    if normalized_provider in {"yt", "youtube music"}:
        normalized_provider = "youtube"
    elif normalized_provider in {"apple music", "music", "apple_music"}:
        normalized_provider = "apple_music"

    if normalized_provider == "spotify":
        return _play_spotify(query, autoplay=autoplay)
    if normalized_provider == "apple_music":
        return _play_apple_music(query, autoplay=autoplay)
    if normalized_provider == "youtube":
        return _play_youtube(query)

    if app_exists("spotify"):
        result = _play_spotify(query, autoplay=autoplay)
        if "acilamadi" not in result:
            return result
    return _play_youtube(query)


def control_media(action: str = "play_pause") -> str:
    normalized = (action or "play_pause").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "durdur": "stop",
        "stop": "stop",
        "kapat": "stop",
        "pause": "pause",
        "duraklat": "pause",
        "beklet": "pause",
        "devam": "resume",
        "resume": "resume",
        "oynat": "resume",
        "play": "resume",
        "play_pause": "play_pause",
        "toggle": "play_pause",
        "sonraki": "next",
        "next": "next",
        "ileri": "next",
        "onceki": "previous",
        "önceki": "previous",
        "previous": "previous",
        "geri": "previous",
        "mute": "mute",
        "sessize_al": "mute",
        "volume_up": "volume_up",
        "ses_artir": "volume_up",
        "volume_down": "volume_down",
        "ses_azalt": "volume_down",
    }
    command = aliases.get(normalized, normalized)
    ok, detail = send_media_key(command)
    if ok:
        labels = {
            "stop": "Medya durdurma komutu gonderildi.",
            "pause": "Medya duraklat/devam komutu gonderildi.",
            "resume": "Medya oynat/devam komutu gonderildi.",
            "play_pause": "Medya oynat/duraklat komutu gonderildi.",
            "next": "Sonraki medya komutu gonderildi.",
            "previous": "Onceki medya komutu gonderildi.",
            "mute": "Sessize alma komutu gonderildi.",
            "volume_up": "Ses artirma komutu gonderildi.",
            "volume_down": "Ses azaltma komutu gonderildi.",
        }
        return labels.get(command, "Medya komutu gonderildi.")
    return detail
