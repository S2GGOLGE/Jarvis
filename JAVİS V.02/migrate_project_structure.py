from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


NEW_PROJECT_STRUCTURE = """
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
    live/
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
"""


MIGRATION_MAP: dict[str, str] = {
    "app_config.py": "config/app_config.py",
    "core/config_live.py": "config/live_config.py",
    "core/Tolls.py": "tools/declarations.py",
    "core/live/jarvislive.py": "core/live/session.py",
    "actions/browser.py": "automation/browser.py",
    "actions/media.py": "automation/media.py",
    "actions/shell.py": "automation/shell.py",
    "actions/system_power.py": "automation/system_power.py",
    "actions/whatsapp.py": "automation/whatsapp.py",
    "actions/windows_utils.py": "automation/windows_utils.py",
    "actions/calendar.py": "integrations/calendar.py",
    "actions/weather.py": "integrations/weather.py",
    "actions/youtube_stats.py": "integrations/youtube_stats.py",
    "actions/reminders.py": "integrations/reminders.py",
    "actions/screen_vision.py": "integrations/screen_vision.py",
    "actions/tts.py": "integrations/tts.py",
    "actions/health.py": "integrations/health.py",
    "actions/open_app.py": "integrations/open_app.py",
    "actions/sys_info.py": "integrations/system_info.py",
    "memory/memory_manager.py": "memory/manager.py",
    "memory/_init_.py": "memory/__init__.py",
    "security.py": "security/owner.py",
    "ui/ui.py": "ui/desktop.py",
    "ui/_init_.py": "ui/__init__.py",
    "Config/api_keys.json": "config/api_keys.json",
    "Config/api_keys.example.json": "config/api_keys.example.json",
    "Icon/youtube.png": "assets/icons/youtube.png",
    "Icon/youtube-logo.png": "assets/icons/youtube-logo.png",
    "Icon/instagram.png": "assets/icons/instagram.png",
    "Icon/instagram-logo.png": "assets/icons/instagram-logo.png",
    "Fonts/Grift-Regular.ttf": "assets/fonts/Grift-Regular.ttf",
    "Fonts/Grift-ExtraBold.ttf": "assets/fonts/Grift-ExtraBold.ttf",
    "Fonts/Grift-Bold.ttf": "assets/fonts/Grift-Bold.ttf",
    "SFX/Think.mp3": "assets/sfx/Think.mp3",
    "SFX/Start.mp3": "assets/sfx/Start.mp3",
    "SFX/HUD.mp3": "assets/sfx/HUD.mp3",
    "SFX/Error.mp3": "assets/sfx/Error.mp3",
    "SFX/Done.mp3": "assets/sfx/Done.mp3",
    "deneme.py": "scripts/deneme.py",
}


DIRECTORIES: tuple[str, ...] = (
    "app",
    "config",
    "core",
    "core/live",
    "tools",
    "automation",
    "integrations",
    "memory",
    "security",
    "ui",
    "assets",
    "assets/icons",
    "assets/fonts",
    "assets/sfx",
    "network",
    "utils",
    "scripts",
)

CASE_DIRECTORY_RENAMES: dict[str, str] = {
    "Config": "config",
}


PACKAGE_INIT_FILES: tuple[str, ...] = (
    "app/__init__.py",
    "config/__init__.py",
    "tools/__init__.py",
    "automation/__init__.py",
    "integrations/__init__.py",
    "security/__init__.py",
    "network/__init__.py",
    "utils/__init__.py",
)


@dataclass
class MigrationEvent:
    action: str
    source: str = ""
    destination: str = ""
    status: str = "ok"
    detail: str = ""


class ProjectMigrator:
    def __init__(
        self,
        root: Path,
        dry_run: bool = True,
        backup_dir_name: str = "backup_before_refactor",
        conflict_mode: str = "skip",
        verify_imports: bool = False,
    ) -> None:
        self.root = root.resolve()
        self.dry_run = dry_run
        self.backup_dir = self.root / backup_dir_name
        self.conflict_mode = conflict_mode
        self.verify_imports = verify_imports
        self.events: list[MigrationEvent] = []
        self.started_at = time.strftime("%Y%m%d-%H%M%S")

    def run(self) -> int:
        self._log("scan", detail=f"root={self.root}")
        if not self.root.exists() or not self.root.is_dir():
            self._log("scan", status="error", detail="root does not exist or is not a directory")
            self._write_report()
            return 2

        self._scan_project()
        self._create_backup()
        self._normalize_case_directories()
        self._create_directories()
        self._move_files()
        self._create_package_init_files()

        if self.verify_imports:
            self._verify_imports()

        self._write_report()
        self._print_summary()
        return 1 if any(event.status == "error" for event in self.events) else 0

    def _scan_project(self) -> None:
        existing = 0
        missing = 0
        for old_path in MIGRATION_MAP:
            if (self.root / old_path).exists():
                existing += 1
            else:
                missing += 1
                self._log("scan", source=old_path, status="missing", detail="source file missing")
        self._log("scan", status="ok", detail=f"existing={existing} missing={missing}")

    def _create_directories(self) -> None:
        for rel_dir in DIRECTORIES:
            target = self.root / rel_dir
            self._log("mkdir", destination=rel_dir, detail="dry-run" if self.dry_run else "")
            if not self.dry_run:
                target.mkdir(parents=True, exist_ok=True)

    def _create_backup(self) -> None:
        if self.dry_run:
            self._log("backup", destination=str(self.backup_dir), detail="dry-run")
            return

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, str] = {}

        for old_rel in MIGRATION_MAP:
            source = self.root / old_rel
            if not source.exists() or not source.is_file():
                continue

            backup_target = self.backup_dir / old_rel
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            if backup_target.exists():
                backup_target = self._with_suffix_stamp(backup_target, ".bak")

            shutil.copy2(source, backup_target)
            manifest[old_rel] = str(backup_target.relative_to(self.root))
            self._log("backup", source=old_rel, destination=str(backup_target.relative_to(self.root)))

        manifest_path = self.backup_dir / f"manifest-{self.started_at}.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._log("backup", destination=str(manifest_path.relative_to(self.root)), detail="manifest written")

    def _normalize_case_directories(self) -> None:
        for old_rel, new_rel in CASE_DIRECTORY_RENAMES.items():
            source = self.root / old_rel
            destination = self.root / new_rel

            if not source.exists() or not source.is_dir():
                continue

            if old_rel == new_rel:
                continue

            same_location = str(source.resolve()).casefold() == str(destination.resolve()).casefold()
            if not same_location and destination.exists():
                self._log(
                    "case-rename",
                    source=old_rel,
                    destination=new_rel,
                    status="conflict",
                    detail="destination directory exists",
                )
                continue

            self._log(
                "case-rename",
                source=old_rel,
                destination=new_rel,
                detail="dry-run" if self.dry_run else "",
            )
            if self.dry_run:
                continue

            if same_location:
                temp_path = source.with_name(f"{source.name}.case_tmp.{self.started_at}")
                os.replace(source, temp_path)
                os.replace(temp_path, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)

    def _move_files(self) -> None:
        for old_rel, new_rel in MIGRATION_MAP.items():
            source = self.root / old_rel
            destination = self.root / new_rel

            if not source.exists():
                continue

            if source.resolve() == destination.resolve():
                self._log("move", source=old_rel, destination=new_rel, status="skip", detail="same path")
                continue

            if destination.exists():
                resolved = self._resolve_conflict(destination)
                if resolved is None:
                    self._log(
                        "move",
                        source=old_rel,
                        destination=new_rel,
                        status="conflict",
                        detail="destination exists; skipped",
                    )
                    continue
                destination = resolved
                new_rel = str(destination.relative_to(self.root)).replace(os.sep, "/")

            self._log(
                "move",
                source=old_rel,
                destination=new_rel,
                detail="dry-run" if self.dry_run else "",
            )
            if not self.dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)

    def _create_package_init_files(self) -> None:
        for rel_file in PACKAGE_INIT_FILES:
            path = self.root / rel_file
            if path.exists():
                self._log("init", destination=rel_file, status="skip", detail="exists")
                continue
            self._log("init", destination=rel_file, detail="dry-run" if self.dry_run else "")
            if not self.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

    def _verify_imports(self) -> None:
        if self.dry_run:
            self._log("verify", status="skip", detail="dry-run")
            return

        checks = (
            "import pathlib; print('python ok')",
            "from automation.browser import browser_control; print('automation.browser ok')",
            "from automation.media import play_media, control_media; print('automation.media ok')",
            "from automation.shell import shell_run; print('automation.shell ok')",
            "from automation.whatsapp import send_whatsapp_message; print('automation.whatsapp ok')",
            "from integrations.screen_vision import analyze_screen; print('integrations.screen_vision ok')",
        )

        for code in checks:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=20,
            )
            if completed.returncode == 0:
                self._log("verify", status="ok", detail=completed.stdout.strip())
            else:
                self._log(
                    "verify",
                    status="error",
                    detail=(completed.stderr or completed.stdout).strip(),
                )

    def _resolve_conflict(self, destination: Path) -> Path | None:
        if self.conflict_mode == "skip":
            return None

        if self.conflict_mode == "overwrite":
            return destination

        if self.conflict_mode == "rename":
            return self._with_suffix_stamp(destination, ".migrated")

        raise ValueError(f"Invalid conflict mode: {self.conflict_mode}")

    def _with_suffix_stamp(self, path: Path, marker: str) -> Path:
        suffix = path.suffix
        stem = path.name[: -len(suffix)] if suffix else path.name
        candidate = path.with_name(f"{stem}{marker}.{self.started_at}{suffix}")
        counter = 1
        while candidate.exists():
            candidate = path.with_name(f"{stem}{marker}.{self.started_at}.{counter}{suffix}")
            counter += 1
        return candidate

    def _write_report(self) -> None:
        report = {
            "root": str(self.root),
            "dry_run": self.dry_run,
            "backup_dir": str(self.backup_dir),
            "conflict_mode": self.conflict_mode,
            "new_project_structure": NEW_PROJECT_STRUCTURE.strip(),
            "migration_map": MIGRATION_MAP,
            "events": [asdict(event) for event in self.events],
        }

        report_path = self.root / f"migration_report_{self.started_at}.json"
        if self.dry_run:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self._log("report", destination=str(report_path.relative_to(self.root)))

    def _print_summary(self) -> None:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.status] = counts.get(event.status, 0) + 1
        print("Migration summary:", json.dumps(counts, ensure_ascii=False, sort_keys=True))
        print("Mode:", "dry-run" if self.dry_run else "apply")
        print("Root:", self.root)

    def _log(
        self,
        action: str,
        source: str = "",
        destination: str = "",
        status: str = "ok",
        detail: str = "",
    ) -> None:
        event = MigrationEvent(
            action=action,
            source=source,
            destination=destination,
            status=status,
            detail=detail,
        )
        self.events.append(event)
        print(
            f"[{status.upper()}] {action}"
            f"{' ' + source if source else ''}"
            f"{' -> ' + destination if destination else ''}"
            f"{' | ' + detail if detail else ''}"
        )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely migrate JARVIS project files into the new architecture."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Project root path. Default: current directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply file operations. Without this flag the script runs dry-run only.",
    )
    parser.add_argument(
        "--backup-dir",
        default="backup_before_refactor",
        help="Backup directory name inside project root.",
    )
    parser.add_argument(
        "--conflict",
        choices=("skip", "rename", "overwrite"),
        default="skip",
        help="How to handle destination conflicts. Default: skip.",
    )
    parser.add_argument(
        "--verify-imports",
        action="store_true",
        help="Run optional import checks after apply.",
    )
    parser.add_argument(
        "--print-tree",
        action="store_true",
        help="Print target project tree and exit.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] = sys.argv[1:]) -> int:
    args = parse_args(argv)

    if args.print_tree:
        print(NEW_PROJECT_STRUCTURE.strip())
        print(json.dumps(MIGRATION_MAP, ensure_ascii=False, indent=2))
        return 0

    migrator = ProjectMigrator(
        root=Path(args.root),
        dry_run=not args.apply,
        backup_dir_name=args.backup_dir,
        conflict_mode=args.conflict,
        verify_imports=args.verify_imports,
    )
    return migrator.run()


if __name__ == "__main__":
    raise SystemExit(main())
