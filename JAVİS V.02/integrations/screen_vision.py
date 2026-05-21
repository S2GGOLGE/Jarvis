from __future__ import annotations

import io
import json
import logging
import tempfile
import time
import warnings
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore", message=".*Python version 3.9 past its end of life.*")
warnings.filterwarnings("ignore", message=".*non-text parts.*")
warnings.filterwarnings("ignore", message=".*inline_data.*")
warnings.filterwarnings("ignore", message=".*concatenated text result.*")

from google import genai
from google.genai import errors, types
from PIL import Image, ImageStat, UnidentifiedImageError

from automation.windows_utils import active_window_screenshot, full_screen_screenshot
from config.app_config import get_app_config_value

LOG = logging.getLogger("jarvis.actions.screen_vision")

VISION_MODELS = (
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.0-flash",
)
VISION_MAX_DIMENSION = 1600
VISION_MAX_INLINE_BYTES = 4_800_000
VISION_RETRY_DELAYS = (0.6, 1.4, 2.8)


@dataclass(frozen=True)
class CaptureMeta:
    image_path: Path
    owner_name: str = ""
    window_title: str = ""
    bounds: dict | None = None
    detail: str = ""


def _screen_permission_message() -> str:
    return (
        "Ekran analizi icin Windows'ta ekran goruntusu alinmasi gerekiyor. "
        "PyAutoGUI yuklu oldugundan ve uygulamanin ekrana erisebildiginden emin ol."
    )


def _normalize_target(target: str) -> str:
    normalized = (target or "active_window").strip().lower().replace("-", "_")
    aliases = {
        "active": "active_window",
        "window": "active_window",
        "aktif_pencere": "active_window",
        "pencere": "active_window",
        "screen": "full_screen",
        "full": "full_screen",
        "fullscreen": "full_screen",
        "full_screen": "full_screen",
        "entire_screen": "full_screen",
        "all_screen": "full_screen",
        "tum_ekran": "full_screen",
        "tüm_ekran": "full_screen",
        "ekran": "full_screen",
        "monitor": "full_screen",
        "monitors": "full_screen",
    }
    return aliases.get(normalized, normalized)


def _capture_screen(mode: str) -> tuple[bool, str, Optional[CaptureMeta]]:
    if mode not in {"capture_active_window", "capture_full_screen"}:
        return False, f"Bilinmeyen ekran modu: {mode}", None

    temp = tempfile.NamedTemporaryFile(prefix="jarvis-screen-", suffix=".png", delete=False)
    image_path = Path(temp.name)
    temp.close()

    try:
        payload = (
            full_screen_screenshot(image_path)
            if mode == "capture_full_screen"
            else active_window_screenshot(image_path)
        )
    except Exception as exc:
        with suppress(Exception):
            image_path.unlink(missing_ok=True)
        return False, f"Ekran goruntusu alinamadi: {exc}", None

    ok, detail, meta = _parse_capture_payload(payload, image_path)
    if not ok:
        with suppress(Exception):
            image_path.unlink(missing_ok=True)
    return ok, detail, meta


def _parse_capture_payload(payload: dict, fallback_path: Path) -> tuple[bool, str, Optional[CaptureMeta]]:
    if not isinstance(payload, dict):
        return False, "Ekran helper verisi beklenen formatta degil.", None

    if not payload.get("ok", False):
        detail = str(payload.get("detail") or payload.get("error") or "Ekran goruntusu alinamadi.")
        low = detail.lower()
        if "permission" in low or "not permitted" in low or "screen recording" in low:
            return False, _screen_permission_message(), None
        return False, detail, None

    image_path = Path(str(payload.get("image_path") or fallback_path))
    return (
        True,
        "",
        CaptureMeta(
            image_path=image_path,
            owner_name=str(payload.get("owner_name", "") or "").strip(),
            window_title=str(payload.get("window_title", "") or "").strip(),
            bounds=payload.get("bounds") or {},
            detail=str(payload.get("detail", "") or "").strip(),
        ),
    )


def _validate_image(image_path: Path) -> tuple[bool, str]:
    if not image_path.exists():
        return False, "Ekran goruntusu dosyasi bulunamadi. Tekrar dene."
    if image_path.stat().st_size <= 0:
        return False, "Ekran goruntusu bos geldi. " + _screen_permission_message()

    try:
        with Image.open(image_path) as img:
            img.verify()
    except (UnidentifiedImageError, OSError):
        return False, "Ekran goruntusu gecersiz veya okunamiyor."

    if _image_looks_blank(image_path):
        return (
            False,
            "Ekran goruntusu siyah veya bos gorunuyor. "
            "Bu, ekran izni eksik oldugunda ya da korumali bir uygulama acikken olabilir. "
            + _screen_permission_message(),
        )
    return True, ""


def _image_looks_blank(image_path: Path) -> bool:
    try:
        with Image.open(image_path) as img:
            sample = img.convert("RGB")
            sample.thumbnail((256, 256), Image.Resampling.BILINEAR)
            stat = ImageStat.Stat(sample)
            extrema = stat.extrema
            mean_total = sum(stat.mean) / max(1, len(stat.mean))
            max_seen = max(channel[1] for channel in extrema)
            return max_seen <= 8 or mean_total <= 3
    except Exception:
        return False


def _build_image_part(image_path: Path) -> types.Part:
    with Image.open(image_path) as img:
        work = img.copy()

    if work.mode not in {"RGB", "L"}:
        work = work.convert("RGB")

    if max(work.size) > VISION_MAX_DIMENSION:
        work.thumbnail((VISION_MAX_DIMENSION, VISION_MAX_DIMENSION), Image.Resampling.LANCZOS)

    png_buffer = io.BytesIO()
    work.save(png_buffer, format="PNG", optimize=True)
    png_bytes = png_buffer.getvalue()
    if len(png_bytes) <= VISION_MAX_INLINE_BYTES:
        return types.Part.from_bytes(data=png_bytes, mime_type="image/png")

    jpg_buffer = io.BytesIO()
    rgb = work.convert("RGB") if work.mode != "RGB" else work
    rgb.save(jpg_buffer, format="JPEG", quality=86, optimize=True)
    return types.Part.from_bytes(data=jpg_buffer.getvalue(), mime_type="image/jpeg")


def _vision_prompt(query: str, meta: CaptureMeta) -> str:
    label = " / ".join(
        part for part in (meta.owner_name, meta.window_title, meta.detail) if part
    ) or "ekran"
    user_query = (query or "Ekranda ne var?").strip()[:500]
    bounds = json.dumps(meta.bounds or {}, ensure_ascii=False)

    return (
        "Sen JARVIS icin Windows ekran analizi yapan dikkatli bir vision asistanisin.\n"
        "Goruntu kullanicinin secili pencere veya ekran hedefinden alindi.\n"
        f"Baglam: {label}\n"
        f"Ekran/pencere sinirlari: {bounds}\n\n"
        "Kurallar:\n"
        "- Sadece goruntude gordugun seyleri soyle.\n"
        "- Hata, uyari, buton, form alani, baslik ve okunabilir metinleri yakala.\n"
        "- Emin olmadigin kisimlarda emin olmadigini belirt.\n"
        "- Kullanici sorusuna dogrudan cevap ver.\n"
        "- Cevabi Turkce, kisa ama yeterli detayla ver.\n\n"
        f"Kullanici sorusu: {user_query}"
    )


def _extract_response_text(response) -> str:
    chunks: list[str] = []

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = str(getattr(part, "text", "") or "").strip()
            if part_text:
                chunks.append(part_text)

    return "\n".join(chunks).strip()


def _is_transient_vision_error(exc: Exception) -> bool:
    if isinstance(exc, (errors.ServerError, TimeoutError)):
        return True

    message = str(exc or "").lower()
    transient_markers = (
        "503",
        "429",
        "deadline",
        "timed out",
        "timeout",
        "unavailable",
        "temporarily unavailable",
        "service unavailable",
        "internal error",
        "busy",
        "overloaded",
        "resource exhausted",
        "try again later",
        "backend error",
        "connection reset",
    )
    return any(marker in message for marker in transient_markers)


def _friendly_vision_error(exc: Exception) -> str:
    message = str(exc or "").lower()
    if any(marker in message for marker in ("quota", "rate limit", "billing", "limit exceeded")):
        return "Gemini vision istegi kota veya hiz limitine takildi. Biraz bekleyip tekrar dene."
    if _is_transient_vision_error(exc):
        return "Gemini vision servisi su anda yogun veya gecici olarak ulasilamiyor. Biraz sonra tekrar dene."
    return f"Gemini vision istegi basarisiz oldu: {exc}"


def _analyze_with_gemini(query: str, meta: CaptureMeta) -> str:
    api_key = str(get_app_config_value("gemini_api_key", "") or "").strip()
    if not api_key:
        return "Gemini API anahtari eksik oldugu icin ekran analizi yapilamadi."

    client = genai.Client(api_key=api_key)
    image_part = _build_image_part(meta.image_path)
    prompt = _vision_prompt(query, meta)
    last_error: Optional[Exception] = None

    for model_name in VISION_MODELS:
        for attempt, delay in enumerate(VISION_RETRY_DELAYS, start=1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[types.Part.from_text(text=prompt), image_part],
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                text = _extract_response_text(response)
                if text:
                    return text
                raise RuntimeError("Gemini gecerli bir ekran analizi metni dondurmedi.")
            except Exception as exc:
                last_error = exc
                if attempt < len(VISION_RETRY_DELAYS) and _is_transient_vision_error(exc):
                    time.sleep(delay)
                    continue
                if _is_transient_vision_error(exc):
                    break
                raise RuntimeError(_friendly_vision_error(exc)) from exc

    raise RuntimeError(_friendly_vision_error(last_error or RuntimeError("Bilinmeyen hata")))


def analyze_screen(query: str, target: str = "active_window") -> str:
    normalized_target = _normalize_target(target)
    if normalized_target not in {"active_window", "full_screen"}:
        return "Screen Vision active_window veya full_screen hedeflerini destekliyor."

    mode = "capture_full_screen" if normalized_target == "full_screen" else "capture_active_window"
    ok, detail, meta = _capture_screen(mode)
    if not ok or meta is None:
        return detail if detail else "Ekran goruntusu alinamadi."

    try:
        valid, validation_error = _validate_image(meta.image_path)
        if not valid:
            return validation_error

        try:
            analysis = _analyze_with_gemini(query, meta)
        except Exception as exc:
            prefix = " / ".join(part for part in (meta.owner_name, meta.window_title) if part)
            if prefix:
                return f"Ekran goruntusu alindi ({prefix}) ama analiz tamamlanamadi: {exc}"
            return f"Ekran goruntusu alindi ama analiz tamamlanamadi: {exc}"

        title = " / ".join(part for part in (meta.owner_name, meta.window_title) if part)
        return f"[Aktif pencere: {title}]\n{analysis}" if title else analysis

    finally:
        with suppress(Exception):
            meta.image_path.unlink(missing_ok=True)
