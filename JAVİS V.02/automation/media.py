from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from automation.browser import browser_control
from automation.windows_utils import app_exists, open_url, press_enter, send_media_key

LOG = logging.getLogger("jarvis.actions.media")

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = BASE_DIR / "memory" / "media_state.json"
MEDIA_LOCK = threading.RLock()
COMMAND_COOLDOWN_SECONDS = 0.18
SPOTIFY_START_DELAY_SECONDS = 1.6


@dataclass
class MediaState:
    provider: str = ""
    query: str = ""
    status: str = "unknown"
    updated_at: float = 0.0
    last_command: str = ""


def _load_state() -> MediaState:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return MediaState(**{k: data.get(k) for k in MediaState.__dataclass_fields__})
    except Exception:
        LOG.debug("media_state_load_failed", exc_info=True)
    return MediaState()


def _save_state(state: MediaState) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        LOG.debug("media_state_save_failed", exc_info=True)


def _update_state(**kwargs) -> None:
    state = _load_state()
    for key, value in kwargs.items():
        if hasattr(state, key):
            setattr(state, key, value)
    state.updated_at = time.time()
    _save_state(state)


def _clean_query(query: Optional[str]) -> str:
    return " ".join(str(query or "").strip().split())[:300]


def _play_youtube(query: str) -> str:
    result = browser_control("play_youtube", query=query)
    _update_state(provider="youtube", query=query, status="playing", last_command="play")
    return result


def _play_spotify(query: str, autoplay: bool = True) -> str:
    encoded_query = urllib.parse.quote(query.strip())
    search_url = f"spotify:search:{encoded_query}"

    if not app_exists("spotify"):
        web_url = f"https://open.spotify.com/search/{encoded_query}"
        if open_url(web_url):
            _update_state(provider="spotify_web", query=query, status="search", last_command="play")
            return f"Spotify Desktop bulunamadi; Spotify Web aramasi acildi: {query}"
        return "Spotify Desktop bulunamadi ve Spotify Web acilamadi."

    if not open_url(search_url):
        return "Spotify acilamadi."

    if not autoplay:
        _update_state(provider="spotify", query=query, status="search", last_command="search")
        return f"Spotify icinde '{query}' aramasi acildi."

    time.sleep(SPOTIFY_START_DELAY_SECONDS)
    ok, detail = press_enter()
    if ok:
        time.sleep(0.45)
        press_enter()
        _update_state(provider="spotify", query=query, status="playing", last_command="play")
        return f"Spotify'da ilk sonuc oynatilmaya calisildi: {query}"

    _update_state(provider="spotify", query=query, status="search", last_command="search")
    return f"Spotify aramasi acildi ama otomatik oynatma tamamlanamadi: {detail}"


def _play_apple_music(query: str, autoplay: bool = True) -> str:
    encoded_query = urllib.parse.quote_plus(query.strip())
    url = f"https://music.apple.com/search?term={encoded_query}"
    if open_url(url):
        _update_state(provider="apple_music", query=query, status="search", last_command="play")
        return f"Apple Music Windows/Web aramasi acildi: {query}"
    return "Apple Music aramasi acilamadi."


def play_media(query: str, provider: str = "auto", autoplay: bool = True) -> str:
    query = _clean_query(query)
    if not query:
        return "Calinacak icerik belirtilmedi."

    normalized_provider = (provider or "auto").strip().lower().replace("-", "_")
    aliases = {
        "yt": "youtube",
        "youtube_music": "youtube",
        "youtube music": "youtube",
        "apple music": "apple_music",
        "music": "apple_music",
    }
    normalized_provider = aliases.get(normalized_provider, normalized_provider)

    with MEDIA_LOCK:
        if normalized_provider == "spotify":
            return _play_spotify(query, autoplay=autoplay)
        if normalized_provider == "apple_music":
            return _play_apple_music(query, autoplay=autoplay)
        if normalized_provider == "youtube":
            return _play_youtube(query)

        if app_exists("spotify"):
            result = _play_spotify(query, autoplay=autoplay)
            if "acilamadi" not in result.lower():
                return result

        return _play_youtube(query)


def _normalize_media_action(action: str) -> str:
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
        "ses_artır": "volume_up",
        "volume_down": "volume_down",
        "ses_azalt": "volume_down",
    }
    return aliases.get(normalized, normalized)


def _status_after_command(command: str) -> str:
    state = _load_state()
    if command == "pause":
        return "paused"
    if command == "resume":
        return "playing"
    if command == "stop":
        return "stopped"
    if command in {"next", "previous", "play_pause"}:
        return "changed"
    return state.status or "unknown"


def control_media(action: str = "play_pause") -> str:
    command = _normalize_media_action(action)

    with MEDIA_LOCK:
        time.sleep(COMMAND_COOLDOWN_SECONDS)
        ok, detail = send_media_key(command)
        if not ok:
            return detail

        status = _status_after_command(command)
        _update_state(status=status, last_command=command)

    labels = {
        "stop": "Medya durdurma komutu gonderildi.",
        "pause": "Medya duraklatma komutu gonderildi.",
        "resume": "Medya oynat/devam komutu gonderildi.",
        "play_pause": "Medya oynat/duraklat komutu gonderildi.",
        "next": "Sonraki medya komutu gonderildi.",
        "previous": "Onceki medya komutu gonderildi.",
        "mute": "Sessize alma komutu gonderildi.",
        "volume_up": "Ses artirma komutu gonderildi.",
        "volume_down": "Ses azaltma komutu gonderildi.",
    }
    return labels.get(command, "Medya komutu gonderildi.")
