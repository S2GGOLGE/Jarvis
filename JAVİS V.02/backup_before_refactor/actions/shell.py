from __future__ import annotations

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Sequence

LOG = logging.getLogger("jarvis.actions.shell")

DEFAULT_TIMEOUT_SECONDS = 20
MAX_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 1200

BLOCKED_PATTERNS = (
    r"\brm\s+-rf\b",
    r"\bdel\s+(/f|/s|/q)\b",
    r"\brmdir\s+(/s|/q)\b",
    r"\brd\s+(/s|/q)\b",
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bbcdedit\b",
    r"\breg\s+delete\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\btaskkill\s+.*(/f|-f)\b",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
)

BLOCKED_SHELL_TOKENS = ("&&", "||", "|", ">", ">>", "<", "`", "$(", "%COMSPEC%")

ALLOWED_EXECUTABLES = {
    "dir",
    "echo",
    "where",
    "whoami",
    "hostname",
    "ipconfig",
    "ping",
    "tracert",
    "nslookup",
    "netstat",
    "tasklist",
    "systeminfo",
    "ver",
    "type",
    "more",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "cmd",
    "cmd.exe",
    "python",
    "python.exe",
    "py",
    "git",
    "git.exe",
}

CMD_BUILTINS = {"dir", "echo", "type", "more", "ver"}

DANGEROUS_POWERSHELL_VERBS = {
    "remove-item",
    "del",
    "erase",
    "ri",
    "rm",
    "move-item",
    "ren",
    "rename-item",
    "set-acl",
    "stop-process",
    "restart-computer",
    "stop-computer",
}


@dataclass(frozen=True)
class ShellResult:
    ok: bool
    message: str
    returncode: int | None = None

    def as_text(self) -> str:
        return self.message


def _tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return []


def _is_dangerous(command: str, tokens: Sequence[str]) -> str:
    lowered = command.lower()

    for token in BLOCKED_SHELL_TOKENS:
        if token.lower() in lowered:
            return f"Guvenlik: Shell kontrol operatoru engellendi -> {token}"

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return "Guvenlik: Tehlikeli sistem komutu engellendi."

    if not tokens:
        return "Komut ayrisitirilamadi."

    executable = tokens[0].strip("\"'").lower()
    if executable not in ALLOWED_EXECUTABLES:
        return f"Guvenlik: '{tokens[0]}' komutu allowlist disinda."

    if executable in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        ps_text = " ".join(tokens[1:]).lower()
        for verb in DANGEROUS_POWERSHELL_VERBS:
            if re.search(rf"\b{re.escape(verb)}\b", ps_text):
                return f"Guvenlik: PowerShell icinde '{verb}' engellendi."

    return ""


def _completed_output(completed: subprocess.CompletedProcess) -> str:
    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    ).strip()

    if not output:
        output = "Komut basariyla calisti (cikti yok)."

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (cikti kisaltildi)"

    return output


def shell_run(command: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    command = str(command or "").strip()
    if not command:
        return "Komut belirtilmedi."

    timeout = max(1, min(int(timeout or DEFAULT_TIMEOUT_SECONDS), MAX_TIMEOUT_SECONDS))
    tokens = _tokenize(command)
    safety_error = _is_dangerous(command, tokens)
    if safety_error:
        return safety_error

    try:
        executable = tokens[0].strip("\"'").lower()
        run_args = (
            ["cmd.exe", "/d", "/c", command]
            if executable in CMD_BUILTINS
            else tokens
        )

        completed = subprocess.run(
            run_args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = _completed_output(completed)
        if completed.returncode != 0:
            return f"Komut hata kodu {completed.returncode} ile bitti:\n{output}"
        return output

    except subprocess.TimeoutExpired:
        return f"Komut zaman asimina ugradi ({timeout}s)."
    except FileNotFoundError:
        return f"Komut bulunamadi: {tokens[0] if tokens else command}"
    except Exception as exc:
        LOG.exception("shell_run_failed")
        return f"Komut calistirilamadi: {exc}"
