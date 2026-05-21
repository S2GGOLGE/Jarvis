from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import requests

from automation.windows_utils import open_url

LOG = logging.getLogger("jarvis.actions.browser")

REQUEST_TIMEOUT_SECONDS = 8
MAX_QUERY_LENGTH = 300
ALLOWED_SCHEMES = {"http", "https"}
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


@dataclass(frozen=True)
class BrowserResult:
    ok: bool
    message: str
    url: str = ""

    def as_text(self) -> str:
        return self.message


def _clean_query(query: Optional[str]) -> str:
    cleaned = " ".join(str(query or "").strip().split())
    return cleaned[:MAX_QUERY_LENGTH]


def _validate_url(raw_url: Optional[str]) -> tuple[bool, str, str]:
    raw = str(raw_url or "").strip()
    if not raw:
        return False, "", "URL belirtilmedi."

    if re.search(r"[\r\n\t]", raw):
        return False, "", "URL gecersiz karakter iceriyor."

    if not urllib.parse.urlsplit(raw).scheme:
        raw = "https://" + raw

    parsed = urllib.parse.urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, "", f"Guvenlik: '{scheme}' URL semasi desteklenmiyor."

    if not parsed.netloc or any(ch in parsed.netloc for ch in " <>\"'"):
        return False, "", "URL alan adi gecersiz."

    safe_url = urllib.parse.urlunsplit(
        (
            scheme,
            parsed.netloc,
            parsed.path or "",
            parsed.query or "",
            "",
        )
    )
    return True, safe_url, ""


def _open_safe_url(url: str) -> BrowserResult:
    try:
        if open_url(url):
            return BrowserResult(True, f"Acildi: {url}", url=url)
        return BrowserResult(False, f"Tarayici acilamadi: {url}", url=url)
    except Exception as exc:
        LOG.exception("browser_open_failed")
        return BrowserResult(False, f"Tarayici acilirken hata olustu: {exc}", url=url)


def _find_first_youtube_video(query: str) -> Optional[str]:
    encoded = urllib.parse.quote_plus(query)
    response = requests.get(
        f"https://www.youtube.com/results?search_query={encoded}",
        headers={"User-Agent": "Mozilla/5.0 JARVIS/1.0"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    seen: set[str] = set()
    for video_id in _VIDEO_ID_RE.findall(response.text):
        if video_id not in seen:
            seen.add(video_id)
            return video_id
    return None


def _search_google(query: str) -> BrowserResult:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded}"
    opened = _open_safe_url(url)
    if opened.ok:
        return BrowserResult(True, f"'{query}' icin arama acildi.", url=url)
    return opened


def _play_youtube(query: str) -> BrowserResult:
    try:
        video_id = _find_first_youtube_video(query)
    except Exception as exc:
        LOG.warning("youtube_direct_lookup_failed: %s", exc)
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        opened = _open_safe_url(url)
        if opened.ok:
            return BrowserResult(
                True,
                f"YouTube ilk sonucu alinamadi; arama sonuclari acildi: {query}",
                url=url,
            )
        return opened

    if not video_id:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        opened = _open_safe_url(url)
        if opened.ok:
            return BrowserResult(
                True,
                f"YouTube'da dogrudan video bulunamadi. Arama sonuclari acildi: {query}",
                url=url,
            )
        return opened

    url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
    opened = _open_safe_url(url)
    if opened.ok:
        return BrowserResult(True, f"YouTube'da oynatiliyor: {query}", url=url)
    return opened


def browser_control(action: str, url: str = None, query: str = None) -> str:
    normalized = (action or "").strip().lower().replace("-", "_").replace(" ", "_")

    if normalized in {"open", "open_url", "url"}:
        ok, safe_url, error = _validate_url(url)
        if not ok:
            return error
        return _open_safe_url(safe_url).as_text()

    if normalized in {"search", "google", "web_search"}:
        cleaned = _clean_query(query)
        if not cleaned:
            return "Arama sorgusu belirtilmedi."
        return _search_google(cleaned).as_text()

    if normalized in {"play_youtube", "youtube_play", "play_music", "youtube"}:
        cleaned = _clean_query(query)
        if not cleaned:
            return "YouTube icin arama sorgusu belirtilmedi."
        return _play_youtube(cleaned).as_text()

    return f"Bilinmeyen tarayici eylemi: {action}"
