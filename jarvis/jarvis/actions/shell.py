"""
Terminal komutu calistirma - Windows PowerShell/cmd.
"""

import subprocess


# Tehlikeli komutları engelle
BLOCKED = [
    "rm -rf /",
    "sudo rm -rf",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "shutdown",
    "reboot",
    "halt",
    "diskutil erase",
    "diskutil apfs deletecontainer",
    "format ",
    "bcdedit",
    "reg delete",
    "del /f",
    "rmdir /s",
    ">:",
]


def shell_run(command: str, timeout: int = 30) -> str:
    if not command:
        return "Komut belirtilmedi."

    cmd_lower = command.lower()
    stripped = command.strip()

    if stripped.startswith(("rm ", "mv ", "cp ", "chmod ", "chown ", "sudo ", "del ", "erase ", "rmdir ", "rd ")):
        return (
            "Guvenlik: Dosya veya yetki degistiren komutlar dogrudan calistirilmiyor. "
            "Daha guvenli ve dar kapsamli bir komut dene."
        )

    for blocked in BLOCKED:
        if blocked in cmd_lower:
            return f"Guvenlik: Bu komut engellendi -> {blocked}"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        if not output:
            return "Komut basariyla calisti (cikti yok)."
        # Cok uzun ciktilari kirp
        if len(output) > 800:
            output = output[:800] + "\n... (cikti kisaltildi)"
        return output
    except subprocess.TimeoutExpired:
        return f"Komut zaman asimina ugradi ({timeout}s)."
    except Exception as e:
        return f"Hata: {e}"
