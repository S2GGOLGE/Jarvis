import sys
from pathlib import Path

# Projenin kök dizinini (JAVİS V.02) sys.path'e ekler, böylece 'config' hatası çözülür.
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.append(root_dir)

import asyncio
import datetime
import traceback
import threading
from google.genai import types
from google import genai
import pyaudio

from ui.ui import JarvisUI
from app_config import get_app_config_value
from memory.memory_manager import (
    load_memory, format_memory_for_prompt,
    update_memory, delete_memory
)
from security import verify_owner_pin, has_owner_pin
from actions.open_app import open_app
from actions.sys_info import sys_info
from actions.weather import get_weather_summary
from actions.calendar import (
    get_calendar_events, add_calendar_event, delete_calendar_event
)
from actions.reminders import get_reminders, add_reminder
from actions.browser import browser_control
from actions.shell import shell_run
from actions.media import play_media, control_media
from actions.youtube_stats import get_youtube_channel_report
from actions.screen_vision import analyze_screen
from actions.whatsapp import (
    send_whatsapp_message, call_whatsapp_contact, save_whatsapp_contact
)
from actions.system_power import system_sleep
# ── Config Yapılandırması ───────────────────────────────────────────────────
from core.live.config_live import (
    LIVE_MODEL, 
    FORMAT, 
    KANALLAR as CHANNELS, 
    SEND_SAMPLE_RATE,
    RECV_SAMPLE_RATE, 
    PARÇA_BOYUT as CHUNK_SIZE, 
    PROMPT_PATH,
    OWNER_PROTECTED_TOOLS, 
    OWNER_LOCK_RE, 
    OWNER_UNLOCK_RE, 
    CONTROL_TOKEN_RE
)


try:
    from config import TOOL_DECLARATIONS
except ImportError:
    TOOL_DECLARATIONS = []

pya = pyaudio.PyAudio()

def get_api_key() -> str:
    return str(get_app_config_value("gemini_api_key", "") or "")


def load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "Sen JARVIS'sin — Windows'ta çalışan kişisel AI asistanı. "
            "Türkçe konuş. Kısa ve net yanıtlar ver. "
            "Araçları kullanarak görevleri tamamla, asla taklit etme."
        )


class JarvisLive:
    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._owner_authorized = False

        self.ui.on_text_command  = self._on_text_command
        self.ui.on_pause_toggle  = self._on_pause_toggle
        self.ui.on_effects_state_change = self._on_effects_state_change
        self._paused             = False

    def _on_pause_toggle(self, paused: bool):
        self._paused = paused

    def _on_effects_state_change(self, enabled: bool):
        pass

    def _focus_ui_section_for_tool(self, tool_name: str, args: dict):
        if tool_name == "sys_info":
            query = str(args.get("query", "")).strip().lower()
            if query in {"time", "saat", "zaman", "date", "tarih"}:
                self.ui.focus_panel("time", duration_ms=5200)
            else:
                self.ui.focus_panel("system", duration_ms=5200)
        elif tool_name == "get_weather":
            self.ui.focus_panel("weather", duration_ms=5600)

    def _on_text_command(self, text: str):
        if self._paused:
            return
        self.ui.write_log(f"Siz: {text}")
        if self._handle_owner_command(text):
            return
        if not self._loop or not self.session:
            self.ui.write_log("ERR: JARVIS bağlantısı henüz hazır değil.")
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _handle_owner_command(self, text: str) -> bool:
        raw = str(text or "").strip()
        if OWNER_LOCK_RE.match(raw):
            self._owner_authorized = False
            self.ui.write_log("JARVIS: Sahip oturumu kilitlendi.")
            self.ui.write_debug("Owner session locked", level="SECURITY")
            return True

        match = OWNER_UNLOCK_RE.match(raw)
        if not match:
            return False

        pin = match.group(1).strip()
        if verify_owner_pin(pin):
            self._owner_authorized = True
            self.ui.write_log("JARVIS: Sahip doğrulandı. Hassas araçlar açıldı.")
            self.ui.write_debug("Owner session unlocked", level="SECURITY")
        else:
            self._owner_authorized = False
            self.ui.write_log("JARVIS: Yetki kodu hatalı veya sahip PIN ayarlı değil.")
            self.ui.write_debug("Owner unlock failed", level="SECURITY")
            self.ui.set_state("ERROR")
        return True

    def _owner_guard_result(self, tool_name: str) -> str | None:
        if tool_name not in OWNER_PROTECTED_TOOLS:
            return None
        if not has_owner_pin():
            return (
                "Güvenlik kilidi aktif ama sahip PIN ayarlı değil. "
                "Terminalde proje klasorunde su komutla PIN ayarla: "
                "py -3.12 -c \"from security import set_owner_pin; set_owner_pin('1234')\""
            )
        if not self._owner_authorized:
            return "Hoşgeldiniz."
        return None

    async def _interrupt_audio(self):
        try:
            if self.audio_in_queue:
                while not self.audio_in_queue.empty():
                    try:
                        self.audio_in_queue.get_nowait()
                    except Exception:
                        break
            if self.session:
                await self.session.send_realtime_input(audio_stream_end=True)
            self.set_speaking(False)
        except Exception:
            pass

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        else:
            self.ui.set_state("LISTENING")

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.ui.write_debug(f"{tool_name}: {short}", level="ERROR")
        self.ui.set_state("ERROR")

    @staticmethod
    def _result_looks_like_error(result) -> bool:
        text = str(result or "").strip().lower()
        if not text:
            return False
        error_markers = (
            "hata", "error", "alinamadi", "alınamadı",
            "bulunamadi", "bulunamadı", "acilamadi", "açılamadı",
            "tamamlanamadi", "tamamlanamadı", "gecersiz", "geçersiz",
            "izin gerekiyor", "izin gerekli", "baglanti", "bağlantı", "gerekli.",
        )
        return any(marker in text for marker in error_markers)

    @staticmethod
    def _should_play_success_sfx(tool_name: str, args: dict, result) -> bool:
        action_tools = {
            "open_app", "add_calendar_event", "add_reminder",
            "delete_calendar_event", "remove_calendar_event",
            "call_whatsapp_contact", "control_media", "system_sleep",
        }
        if tool_name in action_tools:
            return True
        if tool_name == "send_whatsapp_message":
            text = str(result or "").lower()
            if bool(args.get("send_now", False)):
                return "gönderildi" in text or "gonderildi" in text
            return False
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
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_p   = load_system_prompt()
        now     = datetime.datetime.now()
        time_ctx = f"[ŞU ANKİ ZAMAN]\n{now.strftime('%A, %d %B %Y — %H:%M')}\n\n"

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str + "\n\n")
        parts.append(sys_p)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}] if TOOL_DECLARATIONS else [],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=str(get_app_config_value("voice", "Charon") or "Charon")
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        print(f"[JARVIS] 🔧 {name} {args}")
        self.ui.set_state("THINKING")

        loop   = asyncio.get_event_loop()
        result = "Tamam."
        had_exception = False
        guard_result = self._owner_guard_result(name)
        if guard_result:
            self.ui.set_state("ERROR")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": guard_result}
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
                r = await loop.run_in_executor(None, system_sleep)
                result = r or "Windows uyku moduna geciyor."

            elif name == "save_memory":
                cat = args.get("category", "notes")
                key = args.get("key", "")
                val = args.get("value", "")
                if key and val:
                    update_memory({cat: {key: {"value": val}}})
                    print(f"[Memory] 💾 {cat}/{key} = {val}")
                result = "ok"

            elif name == "delete_memory":
                result = delete_memory(
                    args.get("category", ""),
                    args.get("key", ""),
                    args.get("match_text", ""),
                )

            elif name == "open_app":
                r = await loop.run_in_executor(
                    None, lambda: open_app(args.get("app_name", "")))
                result = r or f"{args.get('app_name')} açıldı."

            elif name == "sys_info":
                self._focus_ui_section_for_tool(name, args)
                r = await loop.run_in_executor(
                    None, lambda: sys_info(args.get("query", "all")))
                result = r or "Bilgi alındı."

            elif name == "get_weather":
                self._focus_ui_section_for_tool(name, args)
                r = await loop.run_in_executor(
                    None, lambda: get_weather_summary(args.get("location") or None))
                result = r or "Hava durumu bilgisi alindi."

            elif name == "get_calendar_events":
                r = await loop.run_in_executor(
                    None,
                    lambda: get_calendar_events(
                        args.get("query", "today"),
                        int(args.get("limit", 6) or 6),
                    ),
                )
                result = r or "Takvim bilgisi alindi."

            elif name == "add_calendar_event":
                r = await loop.run_in_executor(
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
                result = r or "Takvim etkinligi eklendi."

            elif name == "delete_calendar_event":
                r = await loop.run_in_executor(
                    None,
                    lambda: delete_calendar_event(
                        args.get("title", ""),
                        args.get("start_iso", ""),
                        args.get("calendar_name", ""),
                        bool(args.get("delete_all_matches", False)),
                    ),
                )
                result = r or "Takvim etkinligi silindi."

            elif name == "get_reminders":
                r = await loop.run_in_executor(
                    None,
                    lambda: get_reminders(
                        args.get("query", "upcoming"),
                        int(args.get("limit", 8) or 8),
                        args.get("list_name", ""),
                    ),
                )
                result = r or "Animsatici bilgisi alindi."

            elif name == "add_reminder":
                r = await loop.run_in_executor(
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
                result = r or "Animsatici eklendi."

            elif name == "browser_control":
                r = await loop.run_in_executor(
                    None, lambda: browser_control(
                        args.get("action"),
                        args.get("url"),
                        args.get("query")
                    ))
                result = r or "Tamam."

            elif name == "shell_run":
                r = await loop.run_in_executor(
                    None, lambda: shell_run(args.get("command", "")))
                result = r or "Komut çalıştırıldı."

            elif name == "play_media":
                r = await loop.run_in_executor(
                    None,
                    lambda: play_media(
                        args.get("query", ""),
                        args.get("provider", "auto"),
                        bool(args.get("autoplay", True)),
                    ),
                )
                result = r or "Medya oynatma başlatıldı."

            elif name == "control_media":
                r = await loop.run_in_executor(
                    None,
                    lambda: control_media(args.get("action", "play_pause")),
                )
                result = r or "Medya komutu gönderildi."

            elif name == "get_youtube_channel_report":
                r = await loop.run_in_executor(
                    None,
                    lambda: get_youtube_channel_report(
                        args.get("query", "overview"),
                        args.get("handle", ""),
                        int(args.get("video_limit", 6) or 6),
                    ),
                )
                result = r or "YouTube kanal raporu alindi."

            elif name == "analyze_screen":
                r = await loop.run_in_executor(
                    None,
                    lambda: analyze_screen(
                        args.get("query", "Ekranda ne var?"),
                        args.get("target", "active_window"),
                    ),
                )
                result = r or "Ekran analizi tamamlandi."

            elif name == "send_whatsapp_message":
                r = await loop.run_in_executor(
                    None,
                    lambda: send_whatsapp_message(
                        args.get("message", ""),
                        args.get("phone_number", ""),
                        args.get("recipient_name", ""),
                        bool(args.get("send_now", False)),
                        args.get("app_target", "auto"),
                    ),
                )
                result = r or "WhatsApp işlemi tamamlandı."

            elif name == "call_whatsapp_contact":
                r = await loop.run_in_executor(
                    None,
                    lambda: call_whatsapp_contact(
                        args.get("phone_number", ""),
                        args.get("recipient_name", ""),
                        args.get("call_type", "voice"),
                    ),
                )
                result = r or "WhatsApp arama işlemi tamamlandı."

            elif name == "save_whatsapp_contact":
                r = await loop.run_in_executor(
                    None,
                    lambda: save_whatsapp_contact(
                        args.get("display_name", ""),
                        args.get("phone_number", ""),
                        args.get("aliases", ""),
                    ),
                )
                result = r or "WhatsApp kişisi kaydedildi."

            else:
                result = f"Bilinmeyen araç: {name}"

        except Exception as e:
            result = f"Hata: {e}"
            had_exception = True
            traceback.print_exc()
            self.speak_error(name, e)

        tool_failed = self._result_looks_like_error(result)
        if tool_failed:
            if not had_exception:
                self.ui.set_state("ERROR")
        elif self._should_play_success_sfx(name, args, result):
            self.ui.play_success_sfx()

        if not tool_failed and not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mikrofon başladı")
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT, channels=CHANNELS,
            rate=SEND_SAMPLE_RATE, input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        try:
            while True:
                data = await asyncio.to_thread(
                    stream.read, CHUNK_SIZE, exception_on_overflow=False)
                with self._speaking_lock:
                    jarvis_speaking = self._is_speaking
                if not jarvis_speaking and not self.ui.muted and not self._paused:
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
        except Exception as e:
            print(f"[JARVIS] ❌ Mikrofon: {e}")
            raise
        finally:
            stream.close()

    async def _receive_audio(self):
        print("[JARVIS] 👂 Alım başladı")
        out_buf, in_buf = [], []
        output_noise = False
        output_noise_samples = []
        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            self.set_speaking(True)
                            raw_txt = sc.output_transcription.text.strip()
                            if raw_txt:
                                txt, had_noise = self._clean_transcript_text(raw_txt)
                                if had_noise:
                                    output_noise = True
                                    if len(output_noise_samples) < 4:
                                        output_noise_samples.append(raw_txt)
                                if txt:
                                    out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = sc.input_transcription.text.strip()
                            if txt:
                                in_buf.append(txt)
                                self.ui.mark_user_activity(True)

                        if sc.turn_complete:
                            self.set_speaking(False)

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"Siz: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"JARVIS: {full_out}")
                                if output_noise_samples:
                                    self.ui.write_debug(
                                        "Kısmen filtrelenen ses transcripti: " + " | ".join(output_noise_samples),
                                        level="WARN",
                                    )
                            elif output_noise:
                                self.ui.write_log("ERR: JARVIS sesli yanıtını çözümlerken bir hata oluştu.")
                                if output_noise_samples:
                                    self.ui.write_debug(
                                        "Filtrelenen ham transcript: " + " | ".join(output_noise_samples),
                                        level="WARN",
                                    )
                                self.ui.set_state("ERROR")
                            out_buf = []
                            output_noise = False
                            output_noise_samples = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses)

        except Exception as e:
            print(f"[JARVIS] ❌ Alım: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Ses çalma başladı")
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT, channels=CHANNELS,
            rate=RECV_SAMPLE_RATE, output=True,
        )
        try:
            while True:
                chunk = await self.audio_in_queue.get()
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Ses: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=get_api_key(),
            http_options={"api_version": "v1alpha"}
        )

        while True:
            if self._paused:
                await asyncio.sleep(1)
                continue

            try:
                print("[JARVIS] 🔌 Bağlanıyor...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)

                    print("[JARVIS] ✅ Bağlandı.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS hazır. Dinliyorum...")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
                self.set_speaking(False)
                self.ui.write_log(f"ERR: JARVIS baglantisi kesildi veya internete ulasilamiyor — {e}")
                self.ui.set_state("ERROR")
                print("[JARVIS] 🔄 3 saniyede yeniden bağlanıyor...")
                await asyncio.sleep(3)