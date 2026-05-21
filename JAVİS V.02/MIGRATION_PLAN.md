# JARVIS Project Migration Plan

## 1. Full New Project Tree

```text
jarvis/
  main.py
  requirements.txt
  pyrightconfig.json
  setup.ps1

  app/
    __init__.py
    bootstrap.py
    runtime.py

  config/
    __init__.py
    app_config.py
    live_config.py
    api_keys.example.json
    api_keys.json

  core/
    __init__.py
    assistant.py
    prompt.txt

  core/live/
    __init__.py
    session.py
    audio_io.py
    message_parser.py
    tool_executor.py
    state.py

  tools/
    __init__.py
    declarations.py
    schema.py
    response.py

  automation/
    __init__.py
    browser.py
    media.py
    shell.py
    system_power.py
    whatsapp.py
    windows_utils.py

  integrations/
    __init__.py
    calendar.py
    weather.py
    youtube_stats.py
    reminders.py
    screen_vision.py
    tts.py
    health.py
    open_app.py
    system_info.py

  memory/
    __init__.py
    manager.py
    memory.example.json
    phone_book.example.json

  security/
    __init__.py
    owner.py

  ui/
    __init__.py
    desktop.py

  assets/
    icons/
    fonts/
    sfx/

  network/
    __init__.py
    tcp_client.py

  utils/
    __init__.py
    logging.py
    paths.py
    text.py
    timing.py

  scripts/
    deneme.py
```

## 2. File Migration Map

```text
main.py -> main.py
app_config.py -> config/app_config.py
core/config_live.py -> config/live_config.py
core/prompt.txt -> core/prompt.txt
core/Tolls.py -> tools/declarations.py
core/live/jarvislive.py -> core/live/session.py

actions/browser.py -> automation/browser.py
actions/media.py -> automation/media.py
actions/shell.py -> automation/shell.py
actions/system_power.py -> automation/system_power.py
actions/whatsapp.py -> automation/whatsapp.py
actions/windows_utils.py -> automation/windows_utils.py

actions/calendar.py -> integrations/calendar.py
actions/weather.py -> integrations/weather.py
actions/youtube_stats.py -> integrations/youtube_stats.py
actions/reminders.py -> integrations/reminders.py
actions/screen_vision.py -> integrations/screen_vision.py
actions/tts.py -> integrations/tts.py
actions/health.py -> integrations/health.py
actions/open_app.py -> integrations/open_app.py
actions/sys_info.py -> integrations/system_info.py

memory/memory_manager.py -> memory/manager.py
memory/memory.example.json -> memory/memory.example.json
memory/phone_book.example.json -> memory/phone_book.example.json
memory/_init_.py -> memory/__init__.py

security.py -> security/owner.py
ui/ui.py -> ui/desktop.py
ui/_init_.py -> ui/__init__.py

Config/api_keys.json -> config/api_keys.json
Config/api_keys.example.json -> config/api_keys.example.json

Icon/* -> assets/icons/*
Fonts/* -> assets/fonts/*
SFX/* -> assets/sfx/*

deneme.py -> scripts/deneme.py
```

## 3. File Split Plan

```text
core/live/jarvislive.py
  -> core/live/session.py
     JarvisLive, run, config build, UI callbacks, text command dispatch

  -> core/live/audio_io.py
     realtime send loop, microphone loop, playback loop, audio cleanup

  -> core/live/message_parser.py
     server message parsing, transcription collection, audio part extraction

  -> core/live/tool_executor.py
     tool execution, owner guard, tool response handling, UI tool focus

  -> core/live/state.py
     paused state, speaking state, playback hold, owner authorization

ui/ui.py
  -> ui/desktop.py initially
  -> later: ui/sound.py, ui/widgets.py, ui/theme.py, ui/panels.py

actions/whatsapp.py
  -> automation/whatsapp.py initially
  -> later: automation/whatsapp_contacts.py, automation/whatsapp_desktop.py, automation/whatsapp_web.py

actions/screen_vision.py
  -> integrations/screen_vision.py initially
  -> later: integrations/vision_capture.py, integrations/vision_gemini.py, integrations/vision_image.py

actions/media.py
  -> automation/media.py initially
  -> later: automation/media_keys.py, automation/media_state.py, automation/media_providers.py
```

## 4. Clean Architecture Layers

```text
core
  Realtime assistant orchestration, live session lifecycle, prompt assembly.

automation
  Desktop automation: browser, media keys, WhatsApp, shell, power, Windows helpers.

integrations
  External service integrations: Gemini vision, calendar, weather, YouTube, reminders.

tools
  Tool declarations, response schema, registry, JSON-safe output.

ui
  Tkinter desktop UI, visual state, sound effects, user command input.

memory
  Memory persistence, contact cache, tool history, state files.

network
  TCP startup/client utilities.

security
  Owner PIN, protected tool checks, authorization helpers.

config
  API keys, app settings, live model/audio config.

utils
  Path helpers, logging, text normalization, retry/timing helpers.
```

## 5. Import Fix Strategy

```text
from app_config import get_app_config_value
-> from config.app_config import get_app_config_value

from core.config_live import ...
-> from config.live_config import ...

from core.Tolls import TOOL_DECLARATIONS
-> from tools.declarations import TOOL_DECLARATIONS

from actions.browser import browser_control
-> from automation.browser import browser_control

from actions.media import play_media, control_media
-> from automation.media import play_media, control_media

from actions.shell import shell_run
-> from automation.shell import shell_run

from actions.system_power import system_sleep
-> from automation.system_power import system_sleep

from actions.whatsapp import ...
-> from automation.whatsapp import ...

from actions.screen_vision import analyze_screen
-> from integrations.screen_vision import analyze_screen

from memory.memory_manager import ...
-> from memory.manager import ...

from security import ...
-> from security.owner import ...

from ui.ui import JarvisUI
-> from ui.desktop import JarvisUI
```

## 6. Decoupling Targets

```text
core/live/session.py
  Must not import low-level action modules after migration phase 2.
  Should depend on tools/tool_executor.py.

core/live/tool_executor.py
  Owns all tool imports.
  Later replace direct imports with registry dict.

automation/*
  Must not import UI.
  Must return plain strings or ToolResult-compatible text.

integrations/*
  Must not import realtime session.
  Blocking APIs stay isolated here and are called through executor.

ui/*
  Must not import actions/tools.
  Emits callbacks only.

config/*
  No imports from core, ui, automation, integrations.
```

## 7. Step By Step Migration Order

```text
1. Create packages:
   app, config, tools, automation, integrations, security, network, utils.

2. Add __init__.py files.

3. Move config files:
   app_config.py -> config/app_config.py
   core/config_live.py -> config/live_config.py
   Config/* -> config/*

4. Add compatibility shims:
   app_config.py imports from config.app_config
   core/config_live.py imports from config.live_config
   security.py imports from security.owner
   actions/*.py import from new automation/integrations modules

5. Move memory manager:
   memory/memory_manager.py -> memory/manager.py
   keep memory/memory_manager.py shim

6. Move automation modules:
   actions/browser.py -> automation/browser.py
   actions/media.py -> automation/media.py
   actions/shell.py -> automation/shell.py
   actions/system_power.py -> automation/system_power.py
   actions/whatsapp.py -> automation/whatsapp.py
   actions/windows_utils.py -> automation/windows_utils.py

7. Move integration modules:
   actions/calendar.py -> integrations/calendar.py
   actions/weather.py -> integrations/weather.py
   actions/youtube_stats.py -> integrations/youtube_stats.py
   actions/reminders.py -> integrations/reminders.py
   actions/screen_vision.py -> integrations/screen_vision.py
   actions/tts.py -> integrations/tts.py
   actions/health.py -> integrations/health.py
   actions/open_app.py -> integrations/open_app.py
   actions/sys_info.py -> integrations/system_info.py

8. Move tool declarations:
   core/Tolls.py -> tools/declarations.py
   add tools/response.py and tools/schema.py
   keep core/Tolls.py shim

9. Move UI:
   ui/ui.py -> ui/desktop.py
   keep ui/ui.py shim

10. Split realtime core:
   core/live/jarvislive.py -> core/live/session.py
   extract audio_io/message_parser/tool_executor/state
   keep core/live/jarvislive.py shim

11. Move assets:
   Icon/* -> assets/icons/*
   Fonts/* -> assets/fonts/*
   SFX/* -> assets/sfx/*
   update UI asset path resolution to use utils.paths

12. Move TCP helper:
   tcp_sunucuya_baglan from main.py -> network/tcp_client.py

13. Update imports repo-wide.

14. Validate imports and runtime.

15. Remove compatibility shims only after all imports pass.

16. Optimize:
   tool registry
   common ToolResult schema
   shared logging config
   shared path resolver
```

## 8. Compatibility Shims

```python
# app_config.py
from config.app_config import *
```

```python
# core/config_live.py
from config.live_config import *
```

```python
# core/live/jarvislive.py
from core.live.session import JarvisLive
```

```python
# ui/ui.py
from ui.desktop import *
```

```python
# memory/memory_manager.py
from memory.manager import *
```

```python
# security.py
from security.owner import *
```

```python
# core/Tolls.py
from tools.declarations import *
```

## 9. Migration Validation Checklist

```text
[ ] All old imports still work through shims
[ ] New imports work directly
[ ] py_compile passes for all .py files
[ ] main.py launches UI
[ ] JarvisLive connects
[ ] Text command sends to session
[ ] Audio loop starts
[ ] Tool declarations load
[ ] WhatsApp tool imports
[ ] Browser tool imports
[ ] Media tool imports
[ ] Shell tool blocks dangerous commands
[ ] Screen vision imports without warning spam
[ ] Memory read/write paths still resolve
[ ] Assets resolve from assets/*
[ ] No behavior changes in public tool function signatures
```
