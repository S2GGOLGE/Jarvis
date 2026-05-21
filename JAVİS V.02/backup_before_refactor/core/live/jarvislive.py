import asyncio
import base64
import datetime
import logging
import sys
import threading
import time
import traceback
import warnings
from pathlib import Path
from typing import Any, Iterable, Optional

warnings.filterwarnings("ignore", message=".*Python version 3.9 past its end of life.*")
warnings.filterwarnings("ignore", message=".*non-text parts.*")
warnings.filterwarnings("ignore", message=".*inline_data.*")
warnings.filterwarnings("ignore", message=".*concatenated text result.*")

import pyaudio
from google import genai
from google.genai import types

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from actions.browser import browser_control
from actions.calendar import (
    add_calendar_event,
    delete_calendar_event,
    get_calendar_events,
)
from actions.media import control_media, play_media
from actions.open_app import open_app
from actions.reminders import add_reminder, get_reminders
from actions.screen_vision import analyze_screen
from actions.shell import shell_run
from actions.sys_info import sys_info
from actions.system_power import system_sleep
from actions.weather import get_weather_summary
from actions.whatsapp import (
    call_whatsapp_contact,
    save_whatsapp_contact,
    send_whatsapp_message,
)
from actions.youtube_stats import get_youtube_channel_report
from app_config import get_app_config_value
from core.config_live import (
    CONTROL_TOKEN_RE,
    FORMAT,
    KANALLAR as CHANNELS,
    LIVE_MODEL,
    OWNER_LOCK_RE,
    OWNER_PROTECTED_TOOLS,
    OWNER_UNLOCK_RE,
    PARÇA_BOYUT as CHUNK_SIZE,
    PROMPT_PATH,
    RECV_SAMPLE_RATE,
    SEND_SAMPLE_RATE,
)
from memory.memory_manager import (
    delete_memory,
    format_memory_for_prompt,
    load_memory,
    update_memory,
)
from security import has_owner_pin, verify_owner_pin
from ui.ui import JarvisUI

try:
    from config import TOOL_DECLARATIONS
except ImportError:
    TOOL_DECLARATIONS = []

PLAYBACK_HOLD_SECONDS = 0.35
MIC_IDLE_SLEEP_SECONDS = 0.01
RECONNECT_DELAY_SECONDS = 3

logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)

pya = pyaudio.PyAudio()


def get_api_key() -> str:
    return str(get_app_config_value("gemini_api_key", "") or "")


def load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "Sen JARVIS'sin. Windows üzerinde çalışan kişisel AI asistanısın. "
            "Türkçe konuş. Kısa ve net yanıtlar ver. "
            "Araçları kullanarak görevleri tamamla, asla taklit etme."
        )


class JarvisLive:
    def __init__(self, ui: JarvisUI):
        self.ui = ui
        self.session = None
        self.audio_in_queue: Optional[asyncio.Queue] = None
        self.out_queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._paused = False
        self._owner_authorized = False

        self._state_lock = threading.RLock()
        self._is_speaking = False
        self._playback_hold_until = 0.0

        self.ui.on_text_command = self._on_text_command
        self.ui.on_pause_toggle = self._on_pause_toggle
        self.ui.on_effects_state_change = self._on_effects_state_change

    def _on_pause_toggle(self, paused: bool):
        with self._state_lock:
            self._paused = bool(paused)

    def _on_effects_state_change(self, enabled: bool):
        pass

    def _ui_call(self, method_name: str, *args, **kwargs):
        method = getattr(self.ui, method_name, None)
        if callable(method):
            try:
                return method(*args, **kwargs)
            except Exception:
                return None
        return None

    def _is_paused(self) -> bool:
        with self._state_lock:
            return self._paused

    def _is_muted(self) -> bool:
        return bool(getattr(self.ui, "muted", False))

    def _is_playback_active(self) -> bool:
        with self._state_lock:
            return self._is_speaking or time.monotonic() < self._playback_hold_until

    def set_speaking(self, value: bool):
        with self._state_lock:
            self._is_speaking = bool(value)
            if value:
                self._playback_hold_until = time.monotonic() + PLAYBACK_HOLD_SECONDS

        self._ui_call("set_state", "SPEAKING" if value else "LISTENING")

    def _extend_playback_hold(self):
        with self._state_lock:
            self._is_speaking = True
            self._playback_hold_until = time.monotonic() + PLAYBACK_HOLD_SECONDS

    def _can_send_mic_audio(self) -> bool:
        return (
            self.session is not None
            and not self._is_paused()
            and not self._is_muted()
            and not self._is_playback_active()
        )

    def _focus_ui_section_for_tool(self, tool_name: str, args: dict):
        if tool_name == "sys_info":
            query = str(args.get("query", "")).strip().lower()
            if query in {"time", "saat", "zaman", "date", "tarih"}:
                self._ui_call("focus_panel", "time", duration_ms=5200)
            else:
                self._ui_call("focus_panel", "system", duration_ms=5200)
        elif tool_name == "get_weather":
            self._ui_call("focus_panel", "weather", duration_ms=5600)

    def _on_text_command(self, text: str):
        if self._is_paused():
            return

        self.ui.write_log(f"Siz: {text}")

        if self._handle_owner_command(text):
            return

        if not self._loop or not self.session or self._loop.is_closed():
            self.ui.write_log("ERR: JARVIS bağlantısı hazır değil.")
            return

        future = asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True,
            ),
            self._loop,
        )
        future.add_done_callback(self._log_async_send_error)

    def _log_async_send_error(self, future):
        try:
            future.result()
        except Exception as e:
            self.ui.write_log(f"ERR: Mesaj gönderilemedi: {e}")

    def _handle_owner_command(self, text: str) -> bool:
        raw = str(text or "").strip()

        if OWNER_LOCK_RE.match(raw):
            self._owner_authorized = False
            self.ui.write_log("JARVIS: Sahip oturumu kilitlendi.")
            self._ui_call("write_debug", "Owner session locked", level="SECURITY")
            return True

        match = OWNER_UNLOCK_RE.match(raw)
        if not match:
            return False

        pin = match.group(1).strip()
        if verify_owner_pin(pin):
            self._owner_authorized = True
            self.ui.write_log("JARVIS: Sahip doğrulandı. Hassas araçlar açıldı.")
            self._ui_call("write_debug", "Owner session unlocked", level="SECURITY")
        else:
            self._owner_authorized = False
            self.ui.write_log("JARVIS: Yetki kodu hatalı veya sahip PIN ayarlı değil.")
            self._ui_call("write_debug", "Owner unlock failed", level="SECURITY")
            self._ui_call("set_state", "ERROR")

        return True

    def _owner_guard_result(self, tool_name: str) -> Optional[str]:
        if tool_name not in OWNER_PROTECTED_TOOLS:
            return None
        if not has_owner_pin():
            return (
                "Güvenlik kilidi aktif ama sahip PIN ayarlı değil. "
                "Terminalde proje klasöründe şu komutla PIN ayarla: "
                "py -3 -c \"from security import set_owner_pin; set_owner_pin('1234')\""
            )
        if not self._owner_authorized:
            return "Hoşgeldiniz."
        return None

    async def _interrupt_audio(self):
        try:
            if self.audio_in_queue:
                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
            if self.session:
                await self.session.send_realtime_input(audio_stream_end=True)
        except Exception:
            pass
        finally:
            self.set_speaking(False)

    def speak_error(self, tool_name: str, error: Exception):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} - {short}")
        self._ui_call("write_debug", f"{tool_name}: {short}", level="ERROR")
        self._ui_call("set_state", "ERROR")

    @staticmethod
    def _result_looks_like_error(result) -> bool:
        text = str(result or "").strip().lower()
        if not text:
            return False
        error_markers = (
            "hata",
            "error",
            "alinamadi",
            "alınamadı",
            "bulunamadi",
            "bulunamadı",
            "acilamadi",
            "açılamadı",
            "tamamlanamadi",
            "tamamlanamadı",
            "gecersiz",
            "geçersiz",
            "izin gerekiyor",
            "izin gerekli",
            "baglanti",
            "bağlantı",
            "gerekli.",
        )
        return any(marker in text for marker in error_markers)

    @staticmethod
    def _should_play_success_sfx(tool_name: str, args: dict, result) -> bool:
        action_tools = {
            "open_app",
            "add_calendar_event",
            "add_reminder",
            "delete_calendar_event",
            "remove_calendar_event",
            "call_whatsapp_contact",
            "control_media",
            "system_sleep",
        }
        if tool_name in action_tools:
            return True
        if tool_name == "send_whatsapp_message":
            text = str(result or "").lower()
            return bool(args.get("send_now", False)) and (
                "gönderildi" in text or "gonderildi" in text
            )
        return False

    @staticmethod
    def _clean_transcript_text(text: str) -> tuple[str, bool]:
        raw = str(text or "")
        had_noise = False
        if CONTROL_TOKEN_RE.search(raw):
            had_noise = True
            raw = CONTROL_TOKEN_RE.sub(" ", raw)

        cleaned = []
        for ch in raw:
            if ch in "\n\r\t" or ord(ch) >= 32:
                cleaned.append(ch)
            else:
                had_noise = True

        normalized = " ".join("".join(cleaned).split())
        return normalized.strip(), had_noise

    def _build_config(self) -> types.LiveConnectConfig:
        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        now = datetime.datetime.now()
        time_ctx = f"[ŞU ANKİ ZAMAN]\n{now.strftime('%A, %d %B %Y - %H:%M')}\n\n"

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str + "\n\n")
        parts.append(load_system_prompt())

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}]
            if TOOL_DECLARATIONS
            else [],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=str(
                            get_app_config_value("voice", "Charon") or "Charon"
                        )
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = str(getattr(fc, "name", "") or "")
        args = dict(getattr(fc, "args", None) or {})
        self._ui_call("set_state", "THINKING")

        loop = asyncio.get_running_loop()
        result = "Tamam."
        had_exception = False

        guard_result = self._owner_guard_result(name)
        if guard_result:
            self._ui_call("set_state", "ERROR")
            return types.FunctionResponse(
                id=getattr(fc, "id", None),
                name=name,
                response={"result": guard_result},
            )

        try:
            if name == "owner_unlock":
                pin = str(args.get("pin", "") or "").strip()
                if verify_owner_pin(pin):
                    self._owner_authorized = True
                    result = "Sahip doğrulandı. Hassas araçlar açıldı."
                else:
                    self._owner_authorized = False
                    result = "Yetki kodu hatalı veya sahip PIN ayarlı değil."

            elif name == "owner_lock":
                self._owner_authorized = False
                result = "Sahip oturumu kilitlendi."

            elif name == "system_sleep":
                result = await loop.run_in_executor(None, system_sleep)
                result = result or "Windows uyku moduna geçiyor."

            elif name == "save_memory":
                cat = args.get("category", "notes")
                key = args.get("key", "")
                val = args.get("value", "")
                if key and val:
                    update_memory({cat: {key: {"value": val}}})
                result = "ok"

            elif name == "delete_memory":
                result = delete_memory(
                    args.get("category", ""),
                    args.get("key", ""),
                    args.get("match_text", ""),
                )

            elif name == "open_app":
                result = await loop.run_in_executor(
                    None,
                    lambda: open_app(args.get("app_name", "")),
                )
                result = result or f"{args.get('app_name')} açıldı."

            elif name == "sys_info":
                self._focus_ui_section_for_tool(name, args)
                result = await loop.run_in_executor(
                    None,
                    lambda: sys_info(args.get("query", "all")),
                )
                result = result or "Bilgi alındı."

            elif name == "get_weather":
                self._focus_ui_section_for_tool(name, args)
                result = await loop.run_in_executor(
                    None,
                    lambda: get_weather_summary(args.get("location") or None),
                )
                result = result or "Hava durumu bilgisi alındı."

            elif name == "get_calendar_events":
                result = await loop.run_in_executor(
                    None,
                    lambda: get_calendar_events(
                        args.get("query", "today"),
                        int(args.get("limit", 6) or 6),
                    ),
                )
                result = result or "Takvim bilgisi alındı."

            elif name == "add_calendar_event":
                result = await loop.run_in_executor(
                    None,
                    lambda: add_calendar_event(
                        args.get("title", ""),
                        args.get("start_iso", ""),
                        args.get("end_iso", ""),
                        args.get("notes", ""),
                        args.get("location", ""),
                        args.get("calendar_name", ""),
                        bool(args.get("all_day", False)),
                    ),
                )
                result = result or "Takvim etkinliği eklendi."

            elif name == "delete_calendar_event":
                result = await loop.run_in_executor(
                    None,
                    lambda: delete_calendar_event(
                        args.get("title", ""),
                        args.get("start_iso", ""),
                        args.get("calendar_name", ""),
                        bool(args.get("delete_all_matches", False)),
                    ),
                )
                result = result or "Takvim etkinliği silindi."

            elif name == "get_reminders":
                result = await loop.run_in_executor(
                    None,
                    lambda: get_reminders(
                        args.get("query", "upcoming"),
                        int(args.get("limit", 8) or 8),
                        args.get("list_name", ""),
                    ),
                )
                result = result or "Anımsatıcı bilgisi alındı."

            elif name == "add_reminder":
                result = await loop.run_in_executor(
                    None,
                    lambda: add_reminder(
                        args.get("title", ""),
                        args.get("due_iso", ""),
                        args.get("notes", ""),
                        args.get("list_name", ""),
                        args.get("priority", ""),
                        bool(args.get("all_day", False)),
                    ),
                )
                result = result or "Anımsatıcı eklendi."

            elif name == "browser_control":
                result = await loop.run_in_executor(
                    None,
                    lambda: browser_control(
                        args.get("action"),
                        args.get("url"),
                        args.get("query"),
                    ),
                )
                result = result or "Tamam."

            elif name == "shell_run":
                result = await loop.run_in_executor(
                    None,
                    lambda: shell_run(args.get("command", "")),
                )
                result = result or "Komut çalıştırıldı."

            elif name == "play_media":
                result = await loop.run_in_executor(
                    None,
                    lambda: play_media(
                        args.get("query", ""),
                        args.get("provider", "auto"),
                        bool(args.get("autoplay", True)),
                    ),
                )
                result = result or "Medya oynatma başlatıldı."

            elif name == "control_media":
                result = await loop.run_in_executor(
                    None,
                    lambda: control_media(args.get("action", "play_pause")),
                )
                result = result or "Medya komutu gönderildi."

            elif name == "get_youtube_channel_report":
                result = await loop.run_in_executor(
                    None,
                    lambda: get_youtube_channel_report(
                        args.get("query", "overview"),
                        args.get("handle", ""),
                        int(args.get("video_limit", 6) or 6),
                    ),
                )
                result = result or "YouTube kanal raporu alındı."

            elif name == "analyze_screen":
                result = await loop.run_in_executor(
                    None,
                    lambda: analyze_screen(
                        args.get("query", "Ekranda ne var?"),
                        args.get("target", "active_window"),
                    ),
                )
                result = result or "Ekran analizi tamamlandı."

            elif name == "send_whatsapp_message":
                result = await loop.run_in_executor(
                    None,
                    lambda: send_whatsapp_message(
                        args.get("message", ""),
                        args.get("phone_number", ""),
                        args.get("recipient_name", ""),
                        bool(args.get("send_now", False)),
                        args.get("app_target", "auto"),
                    ),
                )
                result = result or "WhatsApp işlemi tamamlandı."

            elif name == "call_whatsapp_contact":
                result = await loop.run_in_executor(
                    None,
                    lambda: call_whatsapp_contact(
                        args.get("phone_number", ""),
                        args.get("recipient_name", ""),
                        args.get("call_type", "voice"),
                    ),
                )
                result = result or "WhatsApp arama işlemi tamamlandı."

            elif name == "save_whatsapp_contact":
                result = await loop.run_in_executor(
                    None,
                    lambda: save_whatsapp_contact(
                        args.get("display_name", ""),
                        args.get("phone_number", ""),
                        args.get("aliases", ""),
                    ),
                )
                result = result or "WhatsApp kişisi kaydedildi."

            else:
                result = f"Bilinmeyen araç: {name}"

        except Exception as e:
            result = f"Hata: {e}"
            had_exception = True
            traceback.print_exc()
            self.speak_error(name, e)

        tool_failed = self._result_looks_like_error(result)
        if tool_failed and not had_exception:
            self._ui_call("set_state", "ERROR")
        elif self._should_play_success_sfx(name, args, result):
            self._ui_call("play_success_sfx")

        if not tool_failed and not self._is_muted():
            self._ui_call("set_state", "LISTENING")

        return types.FunctionResponse(
            id=getattr(fc, "id", None),
            name=name,
            response={"result": result},
        )

    async def _send_realtime(self, session):
        if self.out_queue is None:
            return

        while self.session is session:
            chunk = await self.out_queue.get()
            if not self._can_send_mic_audio():
                continue

            await session.send_realtime_input(
                audio=types.Blob(
                    data=chunk,
                    mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                )
            )

    async def _listen_audio(self, session):
        stream = None
        try:
            stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=SEND_SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
            self.ui.write_log("SYS: Mikrofon dinleniyor.")

            while self.session is session:
                data = await asyncio.to_thread(
                    stream.read,
                    CHUNK_SIZE,
                    exception_on_overflow=False,
                )

                if not self._can_send_mic_audio():
                    await asyncio.sleep(MIC_IDLE_SLEEP_SECONDS)
                    continue

                if self.out_queue:
                    try:
                        self.out_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        pass

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.ui.write_log(f"ERR: Mikrofon hatası: {e}")
            raise
        finally:
            if stream:
                await self._close_audio_stream(stream)

    async def _receive_audio(self, session):
        in_buf: list[str] = []
        out_buf: list[str] = []
        output_noise = False
        output_noise_samples: list[str] = []

        while self.session is session:
            async for message in session.receive():
                try:
                    await self._handle_server_message(
                        session,
                        message,
                        in_buf,
                        out_buf,
                        output_noise_samples,
                    )

                    if output_noise_samples:
                        output_noise = True

                    server_content = getattr(message, "server_content", None)
                    if getattr(server_content, "turn_complete", False):
                        self._flush_transcripts(
                            in_buf,
                            out_buf,
                            output_noise,
                            output_noise_samples,
                        )
                        in_buf.clear()
                        out_buf.clear()
                        output_noise = False
                        output_noise_samples.clear()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._ui_call("write_debug", f"Receive packet skipped: {e}", level="WARN")

    async def _handle_server_message(
        self,
        session,
        message: Any,
        in_buf: list[str],
        out_buf: list[str],
        output_noise_samples: list[str],
    ):
        server_content = getattr(message, "server_content", None)
        if server_content is not None:
            self._collect_transcriptions(
                server_content,
                in_buf,
                out_buf,
                output_noise_samples,
            )
            await self._queue_audio_parts(server_content)

        tool_call = getattr(message, "tool_call", None)
        if tool_call is not None:
            await self._handle_tool_call(session, tool_call)

        if getattr(message, "go_away", None) is not None:
            raise RuntimeError("Gemini Live session requested reconnect.")

    def _collect_transcriptions(
        self,
        server_content: Any,
        in_buf: list[str],
        out_buf: list[str],
        output_noise_samples: list[str],
    ):
        input_tr = getattr(server_content, "input_transcription", None)
        input_text = str(getattr(input_tr, "text", "") or "").strip()
        if input_text:
            in_buf.append(input_text)
            self._ui_call("mark_user_activity", True)

        output_tr = getattr(server_content, "output_transcription", None)
        output_text = str(getattr(output_tr, "text", "") or "").strip()
        if output_text:
            self._extend_playback_hold()
            clean_text, had_noise = self._clean_transcript_text(output_text)
            if clean_text:
                out_buf.append(clean_text)
            if had_noise and len(output_noise_samples) < 4:
                output_noise_samples.append(output_text)

    async def _queue_audio_parts(self, server_content: Any):
        if self.audio_in_queue is None:
            return

        for part in self._iter_model_parts(server_content):
            inline_data = getattr(part, "inline_data", None)
            if inline_data is None:
                continue

            mime_type = str(getattr(inline_data, "mime_type", "") or "")
            data = getattr(inline_data, "data", None)
            if not data or not mime_type.startswith("audio/"):
                continue

            audio_bytes = self._coerce_audio_bytes(data)
            if not audio_bytes:
                continue

            self._extend_playback_hold()
            await self.audio_in_queue.put(audio_bytes)

    @staticmethod
    def _coerce_audio_bytes(data: Any) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, bytearray):
            return bytes(data)
        if isinstance(data, memoryview):
            return data.tobytes()
        if isinstance(data, str):
            try:
                return base64.b64decode(data, validate=False)
            except Exception:
                return b""
        return b""

    @staticmethod
    def _iter_model_parts(server_content: Any) -> Iterable[Any]:
        model_turn = getattr(server_content, "model_turn", None)
        parts = getattr(model_turn, "parts", None) if model_turn is not None else None
        if not parts:
            return ()
        return tuple(part for part in parts if part is not None)

    async def _handle_tool_call(self, session, tool_call: Any):
        function_calls = getattr(tool_call, "function_calls", None) or []
        responses = []

        for fc in function_calls:
            if fc is None:
                continue
            responses.append(await self._execute_tool(fc))

        if responses:
            await session.send_tool_response(function_responses=responses)

    def _flush_transcripts(
        self,
        in_buf: list[str],
        out_buf: list[str],
        output_noise: bool,
        output_noise_samples: list[str],
    ):
        full_in = " ".join(in_buf).strip()
        if full_in:
            self.ui.write_log(f"Siz: {full_in}")

        full_out = " ".join(out_buf).strip()
        if full_out:
            self.ui.write_log(f"JARVIS: {full_out}")
            return

        if output_noise:
            self.ui.write_log("ERR: JARVIS sesli yanıtını çözümlerken hata oluştu.")
            if output_noise_samples:
                self._ui_call(
                    "write_debug",
                    "Filtrelenen ham transcript: " + " | ".join(output_noise_samples),
                    level="WARN",
                )
            self._ui_call("set_state", "ERROR")

    async def _play_audio(self, session):
        if self.audio_in_queue is None:
            return

        stream = None
        try:
            stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=RECV_SAMPLE_RATE,
                output=True,
            )

            while self.session is session:
                chunk = await self.audio_in_queue.get()
                if not chunk:
                    continue

                self._extend_playback_hold()
                self._ui_call("set_state", "SPEAKING")
                await asyncio.to_thread(stream.write, chunk)
                self._extend_playback_hold()

                if self.audio_in_queue.empty():
                    await asyncio.sleep(PLAYBACK_HOLD_SECONDS)
                    if self.audio_in_queue.empty():
                        self.set_speaking(False)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.ui.write_log(f"ERR: Ses çıkışı hatası: {e}")
            raise
        finally:
            self.set_speaking(False)
            if stream:
                await self._close_audio_stream(stream)

    @staticmethod
    async def _close_audio_stream(stream):
        try:
            if stream.is_active():
                await asyncio.to_thread(stream.stop_stream)
        except Exception:
            pass
        try:
            await asyncio.to_thread(stream.close)
        except Exception:
            pass

    async def run(self):
        client = genai.Client(
            api_key=get_api_key(),
            http_options={"api_version": "v1alpha"},
        )

        self._loop = asyncio.get_running_loop()

        while True:
            try:
                self._ui_call("set_state", "THINKING")
                self.ui.write_log("SYS: JARVIS bağlanıyor...")

                config = self._build_config()

                async with client.aio.live.connect(
                    model=LIVE_MODEL,
                    config=config,
                ) as session:
                    self.session = session
                    self.audio_in_queue = asyncio.Queue(maxsize=48)
                    self.out_queue = asyncio.Queue(maxsize=8)

                    self._ui_call("set_state", "LISTENING")
                    self.ui.write_log("SYS: JARVIS hazır. Dinliyorum...")

                    tasks = [
                        asyncio.create_task(self._send_realtime(session)),
                        asyncio.create_task(self._listen_audio(session)),
                        asyncio.create_task(self._receive_audio(session)),
                        asyncio.create_task(self._play_audio(session)),
                    ]

                    try:
                        done, pending = await asyncio.wait(
                            tasks,
                            return_when=asyncio.FIRST_EXCEPTION,
                        )
                        for task in done:
                            task.result()
                    finally:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                traceback.print_exc()
                self.set_speaking(False)
                self.session = None
                self.ui.write_log(
                    f"ERR: JARVIS bağlantısı kesildi veya internete ulaşılamıyor - {e}"
                )
                self._ui_call("set_state", "ERROR")
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)
