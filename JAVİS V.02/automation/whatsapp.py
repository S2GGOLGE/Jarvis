from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from automation.windows_utils import (
    click_active_window,
    copy_to_clipboard,
    hotkey,
    open_app,
    open_url,
    press_enter,
)
from memory.manager import load_memory, update_memory

LOG = logging.getLogger("jarvis.actions.whatsapp")

BASE_DIR = Path(__file__).resolve().parent.parent
PHONEBOOK_FILE = BASE_DIR / "memory" / "phone_book.json"
RECENT_FILE = BASE_DIR / "memory" / "whatsapp_recent.json"

WA_LOCK = threading.RLock()
UI_WAIT_SECONDS = 2.8
SEND_WAIT_SECONDS = 1.0
MAX_MESSAGE_LENGTH = 4000


@dataclass(frozen=True)
class Contact:
    display_name: str
    phone: str = ""
    aliases: tuple[str, ...] = ()
    source: str = ""
    key: str = ""


@dataclass(frozen=True)
class WhatsAppResult:
    ok: bool
    message: str
    contact: str = ""
    phone: str = ""

    def as_text(self) -> str:
        return self.message


def _normalize_phone(phone_number: str) -> str:
    digits = re.sub(r"\D+", "", phone_number or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = "90" + digits[1:]
    elif len(digits) == 10:
        digits = "90" + digits

    if len(digits) < 8 or len(digits) > 15:
        raise ValueError("Telefon numarasi gecersiz. Ornek: +905551112233")
    return digits


def _normalize_lookup(text: str) -> str:
    text = (text or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i").replace("İ", "i")
    text = re.sub(r"\s+", " ", text)
    return text


def _contact_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize_lookup(name)).strip("_") or "contact"


def _safe_message(message: str) -> str:
    text = str(message or "").replace("\x00", "").strip()
    return text[:MAX_MESSAGE_LENGTH]


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        LOG.debug("json_load_failed: %s", path, exc_info=True)
    return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        LOG.debug("json_save_failed: %s", path, exc_info=True)


def _load_contacts() -> dict:
    memory = load_memory()
    contacts = memory.get("whatsapp_contacts", {})
    return contacts if isinstance(contacts, dict) else {}


def _entry_to_contact(key: str, entry: Any, source: str) -> Optional[Contact]:
    if not isinstance(entry, dict):
        return None

    display_name = str(entry.get("display_name") or key).strip()
    raw_phone = str(entry.get("value") or entry.get("phone") or "").strip()
    phone = ""
    if raw_phone:
        try:
            phone = _normalize_phone(raw_phone)
        except ValueError:
            phone = ""

    aliases = entry.get("aliases", ())
    if isinstance(aliases, str):
        alias_tuple = tuple(part.strip() for part in aliases.split(",") if part.strip())
    elif isinstance(aliases, list):
        alias_tuple = tuple(str(part).strip() for part in aliases if str(part).strip())
    else:
        alias_tuple = ()

    if not display_name and not phone:
        return None
    return Contact(display_name=display_name, phone=phone, aliases=alias_tuple, source=source, key=key)


def _contact_candidates() -> list[Contact]:
    candidates: list[Contact] = []

    for source_name, source in (
        ("whatsapp", _load_contacts()),
        ("phone_book", _load_json(PHONEBOOK_FILE)),
        ("recent", _load_json(RECENT_FILE)),
    ):
        for key, entry in source.items():
            contact = _entry_to_contact(str(key), entry, source_name)
            if contact:
                candidates.append(contact)

    return candidates


def _match_score(needle: str, candidate: str) -> int:
    candidate_norm = _normalize_lookup(candidate)
    if not needle or not candidate_norm:
        return 0
    if candidate_norm == needle:
        return 300
    if candidate_norm.startswith(needle) or needle.startswith(candidate_norm):
        return 220
    if needle in candidate_norm:
        return 160
    parts = needle.split()
    if parts and all(part in candidate_norm for part in parts):
        return 120
    return 0


def _find_contact(recipient_name: str) -> Optional[Contact]:
    needle = _normalize_lookup(recipient_name)
    best: Optional[Contact] = None
    best_score = 0

    for contact in _contact_candidates():
        names = [contact.display_name, contact.key, *contact.aliases]
        for name in names:
            score = _match_score(needle, name)
            if score > best_score:
                best_score = score
                best = contact

    return best if best_score >= 120 else None


def _remember_recent(contact_name: str, phone: str) -> None:
    if not contact_name and not phone:
        return
    key = _contact_key(contact_name or phone)
    data = _load_json(RECENT_FILE)
    data[key] = {
        "display_name": contact_name or phone,
        "value": f"+{phone}" if phone else "",
        "last_used_at": time.time(),
    }
    _save_json(RECENT_FILE, data)


def save_whatsapp_contact(display_name: str, phone_number: str, aliases: str = "") -> str:
    name = " ".join(str(display_name or "").strip().split())
    if not name:
        return "Kisi adi bos olamaz."

    try:
        normalized_phone = _normalize_phone(phone_number)
    except ValueError as exc:
        return str(exc)

    alias_list = [part.strip() for part in str(aliases or "").split(",") if part.strip()]
    key = _contact_key(name)
    try:
        update_memory(
            {
                "whatsapp_contacts": {
                    key: {
                        "value": f"+{normalized_phone}",
                        "display_name": name,
                        "aliases": alias_list,
                    }
                }
            }
        )
        _remember_recent(name, normalized_phone)
    except Exception as exc:
        LOG.warning("whatsapp_contact_save_failed: %s", exc)
        return f"Kisi dogrulandi ama rehbere kaydedilemedi: {exc}"

    if alias_list:
        return f"{name} WhatsApp kisilerine kaydedildi. Takma adlar: {', '.join(alias_list)}"
    return f"{name} WhatsApp kisilerine kaydedildi."


def _unfold_vcf_lines(text: str) -> list[str]:
    unfolded: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def import_phone_book_from_vcf(vcf_path: str) -> str:
    source = Path(vcf_path).expanduser()
    if not source.exists():
        return f"Rehber dosyasi bulunamadi: {source}"

    try:
        text = source.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return f"Rehber dosyasi okunamadi: {exc}"

    entries: dict[str, dict] = {}
    current_lines: list[str] = []
    imported = 0
    skipped = 0

    def flush_card(lines: list[str]):
        nonlocal imported, skipped
        display_name = ""
        numbers: list[str] = []

        for line in lines:
            upper = line.upper()
            if upper.startswith("FN:"):
                display_name = line.split(":", 1)[1].strip()
            elif upper.startswith("N:") and not display_name:
                parts = [part.strip() for part in line.split(":", 1)[1].split(";") if part.strip()]
                display_name = " ".join(reversed(parts[:2])).strip()
            elif "TEL" in upper and ":" in line:
                numbers.append(line.split(":", 1)[1].strip())

        normalized_numbers: list[str] = []
        for raw_number in numbers:
            try:
                normalized_numbers.append("+" + _normalize_phone(raw_number))
            except ValueError:
                continue

        if not display_name or not normalized_numbers:
            skipped += 1
            return

        key = _contact_key(display_name)
        entries[key] = {
            "display_name": display_name,
            "value": normalized_numbers[0],
            "numbers": normalized_numbers,
            "aliases": [part for part in display_name.split() if len(part) > 1],
            "source": "vcf_import",
        }
        imported += 1

    for line in _unfold_vcf_lines(text):
        if line.upper() == "BEGIN:VCARD":
            current_lines = []
        elif line.upper() == "END:VCARD":
            flush_card(current_lines)
            current_lines = []
        else:
            current_lines.append(line)

    phone_book = _load_json(PHONEBOOK_FILE)
    phone_book.update(entries)
    _save_json(PHONEBOOK_FILE, phone_book)
    return f"{imported} rehber kisisi ice aktarildi, {skipped} kayit atlandi."


def _copy_text(text: str) -> WhatsAppResult:
    try:
        copy_to_clipboard(text)
        return WhatsAppResult(True, "Panoya kopyalandi.")
    except Exception as exc:
        LOG.warning("clipboard_failed: %s", exc)
        return WhatsAppResult(False, f"Pano kullanilamadi: {exc}")


def _open_whatsapp_desktop_via_scheme(phone_number: str, message: str) -> WhatsAppResult:
    encoded_message = urllib.parse.quote(message)
    url = f"whatsapp://send?phone={phone_number}&text={encoded_message}"
    if open_url(url):
        time.sleep(UI_WAIT_SECONDS)
        return WhatsAppResult(True, "WhatsApp Desktop sohbeti acildi.", phone=phone_number)
    return WhatsAppResult(False, "WhatsApp URL scheme acilamadi.", phone=phone_number)


def _open_whatsapp_web(phone_number: str, message: str) -> WhatsAppResult:
    encoded_message = urllib.parse.quote(message)
    url = f"https://web.whatsapp.com/send?phone={phone_number}&text={encoded_message}"
    if open_url(url):
        time.sleep(UI_WAIT_SECONDS)
        return WhatsAppResult(True, "WhatsApp Web sohbeti acildi.", phone=phone_number)
    return WhatsAppResult(False, "WhatsApp Web acilamadi.", phone=phone_number)


def _open_whatsapp_chat_by_name(recipient_name: str) -> WhatsAppResult:
    name = " ".join(str(recipient_name or "").strip().split())
    if not name:
        return WhatsAppResult(False, "Kisi adi belirtilmedi.")

    ok, detail = open_app("WhatsApp")
    if not ok:
        return WhatsAppResult(False, f"WhatsApp Desktop acilamadi: {detail}", contact=name)

    time.sleep(UI_WAIT_SECONDS)
    clip = _copy_text(name)
    if not clip.ok:
        return WhatsAppResult(False, clip.message, contact=name)

    for keys, delay in (
        (("ctrl", "n"), 0.3),
        (("ctrl", "a"), 0.15),
        (("ctrl", "v"), 0.6),
    ):
        ok_key, detail_key = hotkey(*keys, delay=delay)
        if not ok_key:
            return WhatsAppResult(False, detail_key, contact=name)

    ok_enter, detail_enter = press_enter(delay=0.8)
    if not ok_enter:
        return WhatsAppResult(False, detail_enter, contact=name)

    time.sleep(0.6)
    return WhatsAppResult(True, f"WhatsApp Desktop uzerinden {name} sohbeti acildi.", contact=name)


def _paste_message_and_optionally_send(message: str, send_now: bool) -> WhatsAppResult:
    clip = _copy_text(message)
    if not clip.ok:
        return clip

    ok_paste, detail_paste = hotkey("ctrl", "v", delay=0.3)
    if not ok_paste:
        return WhatsAppResult(False, detail_paste)

    if not send_now:
        return WhatsAppResult(True, "Taslak mesaj hazirlandi.")

    ok_enter, detail_enter = press_enter(delay=SEND_WAIT_SECONDS)
    if ok_enter:
        return WhatsAppResult(True, "Mesaj gonderildi.")
    return WhatsAppResult(False, f"Mesaj yapistirildi ama gonderilemedi: {detail_enter}")


def _resolve_contact(recipient_name: str, phone_number: str) -> tuple[str, str, Optional[Contact], str]:
    normalized_phone = ""
    if phone_number and phone_number.strip():
        normalized_phone = _normalize_phone(phone_number)

    resolved_name = " ".join(str(recipient_name or "").strip().split())
    contact = _find_contact(resolved_name) if resolved_name else None
    if contact:
        resolved_name = contact.display_name or resolved_name
        if not normalized_phone and contact.phone:
            normalized_phone = contact.phone

    label = resolved_name or (f"+{normalized_phone}" if normalized_phone else "")
    return resolved_name, normalized_phone, contact, label


def send_whatsapp_message(
    message: str,
    phone_number: str = "",
    recipient_name: str = "",
    send_now: bool = False,
    app_target: str = "auto",
) -> str:
    safe_message = _safe_message(message)
    if not safe_message:
        return "Mesaj bos olamaz."

    target = (app_target or "auto").strip().lower()
    if target not in {"auto", "desktop", "web"}:
        target = "auto"

    try:
        resolved_name, normalized_phone, contact, label = _resolve_contact(recipient_name, phone_number)
    except ValueError as exc:
        return str(exc)

    if not normalized_phone and not resolved_name:
        return "WhatsApp mesaji icin kisi adi veya telefon numarasi gerekli."

    with WA_LOCK:
        if target in {"auto", "desktop"}:
            if normalized_phone:
                opened = _open_whatsapp_desktop_via_scheme(normalized_phone, safe_message)
                if opened.ok:
                    _remember_recent(resolved_name or label, normalized_phone)
                    if not send_now:
                        return f"WhatsApp Desktop icinde {label} icin taslak mesaj acildi."
                    sent = _paste_message_and_optionally_send(safe_message, True)
                    if sent.ok:
                        return f"WhatsApp Desktop uzerinden {label} kisisine mesaj gonderildi."
                    if target == "desktop":
                        return sent.message

            if resolved_name:
                opened = _open_whatsapp_chat_by_name(resolved_name)
                if opened.ok:
                    sent = _paste_message_and_optionally_send(safe_message, send_now)
                    if sent.ok:
                        _remember_recent(resolved_name, normalized_phone)
                        return (
                            f"WhatsApp Desktop uzerinden {resolved_name} kisisine mesaj gonderildi."
                            if send_now
                            else f"WhatsApp Desktop uzerinden {resolved_name} icin taslak mesaj hazirlandi."
                        )
                    if target == "desktop":
                        return sent.message
                elif target == "desktop":
                    return opened.message

        if not normalized_phone:
            return (
                f"'{resolved_name}' icin kayitli telefon numarasi bulunamadi. "
                "Once kisiyi numarasiyla kaydet."
            )

        opened = _open_whatsapp_web(normalized_phone, safe_message)
        if not opened.ok:
            return opened.message

        _remember_recent(resolved_name or label, normalized_phone)
        if not send_now:
            return f"WhatsApp Web icinde {label} icin taslak mesaj acildi."

        sent = _paste_message_and_optionally_send(safe_message, True)
        if sent.ok:
            return f"WhatsApp Web uzerinden {label} kisisine mesaj gonderildi."
        return sent.message


def call_whatsapp_contact(
    phone_number: str = "",
    recipient_name: str = "",
    call_type: str = "voice",
) -> str:
    kind = (call_type or "voice").strip().lower()
    if kind not in {"voice", "video"}:
        kind = "voice"

    try:
        resolved_name, normalized_phone, contact, label = _resolve_contact(recipient_name, phone_number)
    except ValueError as exc:
        return str(exc)

    if not normalized_phone and not resolved_name:
        return "WhatsApp aramasi icin kisi adi veya telefon numarasi gerekli."

    with WA_LOCK:
        opened = (
            _open_whatsapp_desktop_via_scheme(normalized_phone, "")
            if normalized_phone
            else _open_whatsapp_chat_by_name(resolved_name)
        )
        if not opened.ok:
            return opened.message

        x_from_right = 104 if kind == "voice" else 152
        ok_click, click_detail = click_active_window(
            x_from_right=x_from_right,
            y_from_top=54,
            delay=1.0,
        )
        if ok_click:
            _remember_recent(resolved_name or label, normalized_phone)
            call_label = "sesli" if kind == "voice" else "goruntulu"
            return f"WhatsApp uzerinden {label} icin {call_label} arama baslatilmaya calisildi."

        return (
            f"WhatsApp sohbeti acildi ama arama butonuna basilamadi: {click_detail}. "
            "WhatsApp penceresi odakta ve ekranda gorunur olmali."
        )
