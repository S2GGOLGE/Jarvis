"""
Uygulama acma - Windows uygulama baslatma yardimcisi.
"""

from actions.windows_utils import open_app as _open_windows_app


# Kisa isimden Windows uygulama adina esleme
APP_ALIASES = {
    "safari":      "Microsoft Edge",
    "chrome":      "Google Chrome",
    "firefox":     "Firefox",
    "terminal":    "Windows Terminal",
    "iterm":       "Windows Terminal",
    "iterm2":      "Windows Terminal",
    "finder":      "File Explorer",
    "spotify":     "Spotify",
    "vscode":      "Visual Studio Code",
    "vs code":     "Visual Studio Code",
    "code":        "Visual Studio Code",
    "xcode":       "Visual Studio",
    "notion":      "Notion",
    "slack":       "Slack",
    "discord":     "Discord",
    "whatsapp":    "WhatsApp",
    "telegram":    "Telegram",
    "zoom":        "Zoom",
    "mail":        "Mail",
    "calendar":    "Calendar",
    "takvim":      "Calendar",
    "notes":       "Notepad",
    "notlar":      "Notepad",
    "music":       "Spotify",
    "müzik":       "Spotify",
    "photos":      "Photos",
    "fotoğraflar": "Photos",
    "maps":        "Maps",
    "haritalar":   "Maps",
    "calculator":  "Calculator",
    "hesap makinesi": "Calculator",
    "system preferences": "Settings",
    "system settings": "Settings",
    "ayarlar":     "Settings",
    "activity monitor": "Task Manager",
    "aktivite monitörü": "Task Manager",
    "preview":     "Photos",
    "önizleme":    "Photos",
    "textedit":    "Notepad",
    "numbers":     "Excel",
    "pages":       "Word",
    "keynote":     "PowerPoint",
    "figma":       "Figma",
    "postman":     "Postman",
    "docker":      "Docker",
    "sequel pro":  "Sequel Pro",
    "tableplus":   "TablePlus",
}


def open_app(app_name: str) -> str:
    """Uygulamayi acar, basari/hata mesaji dondurur."""
    if not app_name:
        return "Uygulama adi belirtilmedi."

    normalized = app_name.lower().strip()
    resolved   = APP_ALIASES.get(normalized, app_name)

    ok, detail = _open_windows_app(resolved)
    if ok:
        return f"{resolved} acildi."
    return detail
