import os
import re
from pathlib import Path
import pyaudio

# ── Paths (Yollar) ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

if BASE_DIR.name == "live" or BASE_DIR.name == "core":
    BASE_DIR = (
        BASE_DIR.parents[1]
        if BASE_DIR.parent.name == "core"
        else BASE_DIR.parent
    )

PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"

# ── Regex Tanımlamaları (RegEx) ─────────────────────────────────────────────
CONTROL_TOKEN_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

OWNER_UNLOCK_RE = re.compile(
    r"^\s*(?:jarvis\s+)?(?:yetki|owner|sahip)\s+(?:kodu|pin|şifre|sifre)\s+(.+?)\s*$",
    re.IGNORECASE
)

OWNER_LOCK_RE = re.compile(
    r"^\s*(?:jarvis\s+)?(?:kilitle|oturumu\s+kapat|owner\s+lock)\s*$",
    re.IGNORECASE
)

# ── Yetki Korumalı Araçlar ──────────────────────────────────────────────────
OWNER_PROTECTED_TOOLS = {
    "save_memory",
    "delete_memory",
    "open_app",
    "takvim_etkinlikleri Al",
    "ekle_takvim_etkinlik",
    "sil_takvim_etkinlik",
    "hatırlatmak",
    "hatırlatma ekle",
    "tarayıcı_kontrol",
    "kabuk_koş",
    "play_media",
    "kontrol_medya",
    "ekranı analiz et",
    "whatsapp_message gönder",
    "çağrı_whatsapp_contact",
    "save_whatsapp_contact",
    "sistem_uyku",
}

# ── Yapay Zeka Model Ayarları ───────────────────────────────────────────────
LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# ── Ses Ayarları ────────────────────────────────────────────────────────────
FORMAT = pyaudio.paInt16
KANALLAR = 1
SEND_SAMPLE_RATE = 16000
RECV_SAMPLE_RATE = 24000
PARÇA_BOYUT = 1024

# ── PyAudio Başlatma ────────────────────────────────────────────────────────
pya = pyaudio.PyAudio()
