"""
TTS (Text-to-Speech) - Windows SAPI/pyttsx3 kullanir.
"""

import threading


VOICE = ""


def speak_text(text: str, on_done=None, blocking: bool = False):
    """
    Metni sesli olarak okur.
    on_done: okuma bitince çağrılacak fonksiyon (opsiyonel)
    blocking: True ise bitene kadar bekler
    """
    if not text or not text.strip():
        if on_done:
            on_done()
        return

    # Çok uzun metinleri kısalt (TTS için)
    max_len = 500
    if len(text) > max_len:
        text = text[:max_len] + "..."

    def _run():
        try:
            import pyttsx3

            engine = pyttsx3.init()
            if VOICE:
                for voice in engine.getProperty("voices"):
                    if VOICE.casefold() in (voice.name or "").casefold():
                        engine.setProperty("voice", voice.id)
                        break
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass
        if on_done:
            on_done()

    if blocking:
        _run()
    else:
        threading.Thread(target=_run, daemon=True).start()


def get_available_voices() -> list[str]:
    """Windows'taki mevcut SAPI seslerini listeler."""
    try:
        import pyttsx3

        engine = pyttsx3.init()
        voices = [voice.name for voice in engine.getProperty("voices") if getattr(voice, "name", "")]
        engine.stop()
        return voices
    except Exception:
        return []
