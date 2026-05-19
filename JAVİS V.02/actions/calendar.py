"""
Windows takvim okuma araci.

Takvim verisini Windows'ta Outlook COM uzerinden okur.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
TR_WEEKDAYS = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma", "Cumartesi", "Pazar"]
TR_MONTHS = ["", "Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran", "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"]


def _month_start(value: dt.datetime) -> dt.datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(value: dt.datetime, months: int) -> dt.datetime:
    total = (value.year * 12 + (value.month - 1)) + months
    year = total // 12
    month = total % 12 + 1
    return value.replace(year=year, month=month, day=1)


def _range_payload(start: dt.datetime, end: dt.datetime) -> dict:
    return {
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
    }


def _normalize_query(query: str) -> dict:
    q = (query or "today").strip().lower()
    now = dt.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    month_match = re.search(r"(\d+)\s*(ay|month|months)", q)
    if "gelecek ay" in q or "önümüzdeki ay" in q or "onumuzdeki ay" in q or "next month" in q:
        start = _add_months(_month_start(now), 1)
        end = _add_months(start, 1)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": 24,
            "kind": "next_month",
            "header": "Gelecek ay icin {count} etkinlik buldum:",
            "empty": "Gelecek ay takviminde etkinlik gorunmuyor.",
        }
    if "bu ay" in q or "this month" in q:
        start = _month_start(now)
        end = _add_months(start, 1)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": 24,
            "kind": "this_month",
            "header": "Bu ay icin {count} etkinlik buldum:",
            "empty": "Bu ay takviminde etkinlik gorunmuyor.",
        }
    if month_match:
        months = max(1, min(12, int(month_match.group(1))))
        start = today_start
        end = _add_months(_month_start(now), months)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": min(60, max(12, months * 12)),
            "kind": "months",
            "header": f"Onumuzdeki {months} ay icin {{count}} etkinlik buldum:",
            "empty": f"Onumuzdeki {months} ayda takviminde etkinlik gorunmuyor.",
        }

    week_match = re.search(r"(\d+)\s*(hafta|week|weeks)", q)
    if week_match:
        weeks = max(1, min(12, int(week_match.group(1))))
        start = today_start
        end = today_start + dt.timedelta(days=weeks * 7)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": min(60, max(8, weeks * 8)),
            "kind": "weeks",
            "header": f"Onumuzdeki {weeks} hafta icin {{count}} etkinlik buldum:",
            "empty": f"Onumuzdeki {weeks} haftada takviminde etkinlik gorunmuyor.",
        }

    day_match = re.search(r"(\d+)\s*(g[uü]n|gun|day|days)", q)
    if day_match:
        days = max(1, min(365, int(day_match.group(1))))
        start = today_start
        end = today_start + dt.timedelta(days=days)
        return {
            "helper_mode": "range",
            "payload": _range_payload(start, end),
            "default_limit": min(60, max(8, days * 2)),
            "kind": "days",
            "header": f"Onumuzdeki {days} gun icin {{count}} etkinlik buldum:",
            "empty": f"Onumuzdeki {days} gunde takviminde etkinlik gorunmuyor.",
        }

    if any(token in q for token in ("yarin", "tomorrow")):
        return {
            "helper_mode": "tomorrow",
            "payload": None,
            "default_limit": 6,
            "kind": "tomorrow",
            "header": "Yarin icin {count} etkinlik buldum:",
            "empty": "Yarin takviminde etkinlik gorunmuyor.",
        }
    if any(token in q for token in ("hafta", "week", "7 gun")):
        return {
            "helper_mode": "week",
            "payload": None,
            "default_limit": 10,
            "kind": "week",
            "header": "Onumuzdeki 7 gun icin {count} etkinlik buldum:",
            "empty": "Onumuzdeki 7 gunde takviminde etkinlik gorunmuyor.",
        }
    if any(token in q for token in ("siradaki", "sıradaki", "sonraki", "next")):
        return {
            "helper_mode": "next",
            "payload": None,
            "default_limit": 1,
            "kind": "next",
            "header": "",
            "empty": "Siradaki takvim etkinligini bulamadim.",
        }
    if any(token in q for token in ("ajanda", "agenda", "yaklasan", "yaklaşan", "upcoming")):
        return {
            "helper_mode": "agenda",
            "payload": None,
            "default_limit": 8,
            "kind": "agenda",
            "header": "Yaklasan ajandanda {count} etkinlik var:",
            "empty": "Yaklasan takvim etkinligi gorunmuyor.",
        }
    return {
        "helper_mode": "today",
        "payload": None,
        "default_limit": 6,
        "kind": "today",
        "header": "Bugun icin {count} etkinlik buldum:",
        "empty": "Bugun takviminde etkinlik gorunmuyor.",
    }


def _run_helper(mode: str, payload: dict | None = None, timeout: int = 20) -> tuple[bool, str]:
    try:
        import win32com.client
    except Exception as exc:
        return False, f"Outlook takvim erisimi icin pywin32 gerekli: {exc}"

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        calendar = namespace.GetDefaultFolder(9)
    except Exception as exc:
        return False, f"Outlook takvimi acilamadi: {exc}"

    try:
        if mode == "create_event":
            created = _outlook_create_event(outlook, payload or {})
            return True, json.dumps({"ok": True, "created": created}, ensure_ascii=False)
        if mode == "delete_event":
            deleted, matches = _outlook_delete_event(calendar, payload or {})
            if deleted:
                return True, json.dumps({"ok": True, "deleted": deleted}, ensure_ascii=False)
            return True, json.dumps({"ok": False, "detail": "Eslesen etkinlik bulunamadi.", "matches": matches}, ensure_ascii=False)
        if mode == "create_reminder":
            created = _outlook_create_task(outlook, payload or {})
            return True, json.dumps({"ok": True, "created": created}, ensure_ascii=False)
        if mode == "reminders_list":
            tasks_folder = namespace.GetDefaultFolder(13)
            reminders = _outlook_get_tasks(tasks_folder, payload or {})
            return True, json.dumps({"ok": True, "reminders": reminders}, ensure_ascii=False)

        events = _outlook_get_events(calendar, mode, payload)
        if mode == "next" and events:
            events = events[:1]
        return True, json.dumps({"ok": True, "events": events}, ensure_ascii=False)
    except Exception as exc:
        return False, f"Outlook takvim islemi basarisiz: {exc}"


def _to_timestamp(value) -> int:
    if isinstance(value, dt.datetime):
        return int(value.timestamp())
    return int(dt.datetime.fromisoformat(str(value)).timestamp())


def _event_to_dict(item) -> dict:
    start = item.Start
    end = item.End
    return {
        "start_ts": _to_timestamp(start),
        "end_ts": _to_timestamp(end),
        "calendar": "Outlook",
        "title": str(getattr(item, "Subject", "") or "").strip() or "Adsiz etkinlik",
        "location": str(getattr(item, "Location", "") or "").strip(),
        "all_day": bool(getattr(item, "AllDayEvent", False)),
    }


def _mode_range(mode: str, payload: dict | None) -> tuple[dt.datetime, dt.datetime]:
    now = dt.datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if mode == "tomorrow":
        start = today_start + dt.timedelta(days=1)
        return start, start + dt.timedelta(days=1)
    if mode == "week":
        return today_start, today_start + dt.timedelta(days=7)
    if mode in {"agenda", "next"}:
        return now, today_start + dt.timedelta(days=60)
    if mode == "range" and payload:
        return dt.datetime.fromisoformat(payload["start_iso"]), dt.datetime.fromisoformat(payload["end_iso"])
    return today_start, today_start + dt.timedelta(days=1)


def _outlook_get_events(calendar, mode: str, payload: dict | None) -> list[dict]:
    start, end = _mode_range(mode, payload)
    items = calendar.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    restriction = (
        f"[Start] < '{end.strftime('%m/%d/%Y %I:%M %p')}' AND "
        f"[End] >= '{start.strftime('%m/%d/%Y %I:%M %p')}'"
    )
    restricted = items.Restrict(restriction)
    events = [_event_to_dict(item) for item in restricted]
    events.sort(key=lambda event: (event["start_ts"], event["title"].lower()))
    return events


def _outlook_create_event(outlook, payload: dict) -> dict:
    item = outlook.CreateItem(1)
    item.Subject = payload.get("title", "")
    item.Start = dt.datetime.fromisoformat(payload.get("start_iso", "")).strftime("%m/%d/%Y %I:%M %p")
    end_iso = payload.get("end_iso", "")
    if end_iso:
        item.End = dt.datetime.fromisoformat(end_iso).strftime("%m/%d/%Y %I:%M %p")
    else:
        item.Duration = 60
    item.Body = payload.get("notes", "")
    item.Location = payload.get("location", "")
    item.AllDayEvent = bool(payload.get("all_day", False))
    item.Save()
    return _event_to_dict(item)


def _outlook_delete_event(calendar, payload: dict) -> tuple[dict | None, list[dict]]:
    title = str(payload.get("title", "")).casefold()
    start, end = _mode_range("range", {
        "start_iso": payload.get("start_iso") or dt.datetime.now().isoformat(),
        "end_iso": (dt.datetime.now() + dt.timedelta(days=365)).isoformat(),
    })
    if payload.get("start_iso"):
        end = start + dt.timedelta(days=1)
    events = _outlook_get_events(calendar, "range", {"start_iso": start.isoformat(), "end_iso": end.isoformat()})
    matches = [event for event in events if title in event["title"].casefold()]
    if not matches:
        return None, []
    target = matches[0]
    for item in calendar.Items:
        try:
            if str(getattr(item, "Subject", "") or "").strip() == target["title"] and _to_timestamp(item.Start) == target["start_ts"]:
                item.Delete()
                break
        except Exception:
            continue
    return target, matches[:3]


def _task_to_dict(item) -> dict:
    due = getattr(item, "DueDate", None)
    due_ts = 0
    if due:
        try:
            due_ts = _to_timestamp(due)
        except Exception:
            due_ts = 0
    return {
        "title": str(getattr(item, "Subject", "") or "").strip() or "Adsiz animsatici",
        "list_name": "Outlook Tasks",
        "notes": str(getattr(item, "Body", "") or "").strip(),
        "completed": bool(getattr(item, "Complete", False)),
        "priority": int(getattr(item, "Importance", 1) or 1),
        "due_ts": due_ts,
        "all_day": True,
    }


def _outlook_get_tasks(tasks_folder, payload: dict) -> list[dict]:
    query = str(payload.get("query", "upcoming") or "upcoming")
    limit = int(payload.get("limit", 8) or 8)
    now = dt.datetime.now()
    today = now.date()
    tasks = []
    for item in tasks_folder.Items:
        task = _task_to_dict(item)
        if task["completed"]:
            continue
        due_date = dt.datetime.fromtimestamp(task["due_ts"]).date() if task["due_ts"] else None
        if query == "today" and due_date != today:
            continue
        if query == "overdue" and (not due_date or due_date >= today):
            continue
        tasks.append(task)
    tasks.sort(key=lambda item: (item["due_ts"] <= 0, item["due_ts"] or 0, item["title"].lower()))
    if query == "next":
        return tasks[:1]
    return tasks[:limit]


def _outlook_create_task(outlook, payload: dict) -> dict:
    item = outlook.CreateItem(3)
    item.Subject = payload.get("title", "")
    item.Body = payload.get("notes", "")
    if payload.get("due_iso"):
        due_raw = str(payload.get("due_iso"))
        if "T" in due_raw or " " in due_raw:
            item.DueDate = dt.datetime.fromisoformat(due_raw).strftime("%m/%d/%Y %I:%M %p")
        else:
            item.DueDate = dt.date.fromisoformat(due_raw).strftime("%m/%d/%Y")
    priority = str(payload.get("priority", "")).lower()
    if priority in {"high", "yuksek", "yüksek", "1"}:
        item.Importance = 2
    item.Save()
    return _task_to_dict(item)


def _parse_payload(raw: str) -> tuple[bool, str, list[dict]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz takvim yaniti alindi.", []

    if not isinstance(payload, dict):
        return False, "Takvim verisi beklenen formatta degil.", []

    if not payload.get("ok", False):
        return False, str(payload.get("detail") or payload.get("error") or "Takvim erisimi basarisiz."), []

    events = payload.get("events", [])
    if not isinstance(events, list):
        return False, "Takvim olaylari okunamadi.", []

    normalized: list[dict] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        try:
            start_ts = int(item.get("start_ts", 0))
            end_ts = int(item.get("end_ts", 0))
        except (TypeError, ValueError):
            continue
        if start_ts <= 0 or end_ts <= 0:
            continue
        normalized.append(
            {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "calendar": str(item.get("calendar", "")).strip(),
                "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
                "location": str(item.get("location", "")).strip(),
                "all_day": bool(item.get("all_day", False)),
            }
        )

    normalized.sort(key=lambda event: (event["start_ts"], event["title"].lower()))
    return True, "", normalized


def _parse_single_event_payload(raw: str) -> tuple[bool, str, dict | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz takvim yaniti alindi.", None

    if not isinstance(payload, dict):
        return False, "Takvim verisi beklenen formatta degil.", None

    if not payload.get("ok", False):
        return False, str(payload.get("detail") or payload.get("error") or "Takvim islemi basarisiz."), None

    item = payload.get("created")
    if not isinstance(item, dict):
        return False, "Olusturulan etkinlik bilgisi alinamadi.", None

    try:
        start_ts = int(item.get("start_ts", 0))
        end_ts = int(item.get("end_ts", 0))
    except (TypeError, ValueError):
        return False, "Olusturulan etkinlik zamani okunamadi.", None

    if start_ts <= 0 or end_ts <= 0:
        return False, "Olusturulan etkinlik zamani gecersiz.", None

    return True, "", {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "calendar": str(item.get("calendar", "")).strip(),
        "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
        "location": str(item.get("location", "")).strip(),
        "all_day": bool(item.get("all_day", False)),
    }


def _parse_deleted_event_payload(raw: str) -> tuple[bool, str, dict | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Gecersiz takvim yaniti alindi.", None

    if not isinstance(payload, dict):
        return False, "Takvim verisi beklenen formatta degil.", None

    if not payload.get("ok", False):
        detail = str(payload.get("detail") or payload.get("error") or "Takvim silme islemi basarisiz.")
        matches = payload.get("matches")
        if isinstance(matches, list) and matches:
            preview = []
            now = dt.datetime.now()
            for item in matches[:3]:
                if not isinstance(item, dict):
                    continue
                try:
                    event = {
                        "start_ts": int(item.get("start_ts", 0)),
                        "end_ts": int(item.get("end_ts", 0)),
                        "calendar": str(item.get("calendar", "")).strip(),
                        "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
                        "location": str(item.get("location", "")).strip(),
                        "all_day": bool(item.get("all_day", False)),
                    }
                except (TypeError, ValueError):
                    continue
                if event["start_ts"] > 0 and event["end_ts"] > 0:
                    preview.append(_format_event_line(event, now))
            if preview:
                detail += " Eslesen etkinlikler: " + " | ".join(preview)
        return False, detail, None

    item = payload.get("deleted")
    if not isinstance(item, dict):
        return False, "Silinen etkinlik bilgisi alinamadi.", None

    try:
        start_ts = int(item.get("start_ts", 0))
        end_ts = int(item.get("end_ts", 0))
    except (TypeError, ValueError):
        return False, "Silinen etkinlik zamani okunamadi.", None

    if start_ts <= 0 or end_ts <= 0:
        return False, "Silinen etkinlik zamani gecersiz.", None

    return True, "", {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "calendar": str(item.get("calendar", "")).strip(),
        "title": str(item.get("title", "")).strip() or "Adsiz etkinlik",
        "location": str(item.get("location", "")).strip(),
        "all_day": bool(item.get("all_day", False)),
    }


def _calendar_permission_message() -> str:
    return (
        "Takvim erisimi icin Windows'ta Outlook ve pywin32 gerekli. "
        "Outlook hesabin acik oldugundan emin ol."
    )


def _day_label(when: dt.datetime, now: dt.datetime) -> str:
    today = now.date()
    target = when.date()
    if target == today:
        return "bugun"
    if target == today + dt.timedelta(days=1):
        return "yarin"
    return f"{when.day} {TR_MONTHS[when.month]} {TR_WEEKDAYS[when.weekday()]}"


def _format_time_range(event: dict, now: dt.datetime) -> str:
    start = dt.datetime.fromtimestamp(event["start_ts"])
    end = dt.datetime.fromtimestamp(event["end_ts"])
    prefix = _day_label(start, now)
    if event["all_day"]:
        return f"{prefix} tum gun"
    return f"{prefix} {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _format_event_line(event: dict, now: dt.datetime) -> str:
    pieces = [f"{_format_time_range(event, now)} - {event['title']}"]
    if event["calendar"]:
        pieces.append(f"[{event['calendar']}]")
    if event["location"]:
        pieces.append(f"@ {event['location']}")
    return " ".join(pieces)


def get_calendar_events(query: str = "today", limit: int = 6) -> str:
    window = _normalize_query(query)
    limit = max(1, min(60, int(limit or window["default_limit"])))

    ok, raw = _run_helper(
        window["helper_mode"],
        payload=window.get("payload"),
        timeout=20,
    )
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _calendar_permission_message()
        return f"Takvim okunamadi: {raw}"

    parsed_ok, detail, events = _parse_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _calendar_permission_message()
        return f"Takvim okunamadi: {detail}"

    now = dt.datetime.now()
    if window["kind"] in {"next", "agenda"}:
        events = [event for event in events if event["end_ts"] >= int(now.timestamp())]

    if not events:
        return window["empty"]

    if window["kind"] == "next":
        return f"Siradaki etkinlik: {_format_event_line(events[0], now)}."

    selected = events[:limit]
    header = str(window["header"]).format(count=len(selected))

    lines = [header]
    for event in selected:
        lines.append(f"- {_format_event_line(event, now)}")
    return "\n".join(lines)


def add_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str = "",
    notes: str = "",
    location: str = "",
    calendar_name: str = "",
    all_day: bool = False,
) -> str:
    title = (title or "").strip()
    start_iso = (start_iso or "").strip()
    if not title:
        return "Takvime eklemek icin etkinlik basligi gerekli."
    if not start_iso:
        return "Takvime eklemek icin baslangic tarihi gerekli."

    payload = {
        "title": title,
        "start_iso": start_iso,
        "end_iso": (end_iso or "").strip(),
        "notes": (notes or "").strip(),
        "location": (location or "").strip(),
        "calendar_name": (calendar_name or "").strip(),
        "all_day": bool(all_day),
    }

    ok, raw = _run_helper("create_event", payload=payload, timeout=25)
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _calendar_permission_message()
        return f"Takvim etkinligi eklenemedi: {raw}"

    parsed_ok, detail, event = _parse_single_event_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _calendar_permission_message()
        return f"Takvim etkinligi eklenemedi: {detail}"

    assert event is not None
    now = dt.datetime.now()
    line = _format_event_line(event, now)
    return f"Takvime eklendi: {line}."


def delete_calendar_event(
    title: str,
    start_iso: str = "",
    calendar_name: str = "",
    delete_all_matches: bool = False,
) -> str:
    title = (title or "").strip()
    if not title:
        return "Takvimden silmek icin etkinlik basligi gerekli."

    payload = {
        "title": title,
        "start_iso": (start_iso or "").strip(),
        "calendar_name": (calendar_name or "").strip(),
        "delete_all_matches": bool(delete_all_matches),
    }

    ok, raw = _run_helper("delete_event", payload=payload, timeout=25)
    if not ok:
        detail = raw.lower()
        if "permission_denied" in detail or "not authorized" in detail or "mach error 4099" in detail:
            return _calendar_permission_message()
        return f"Takvim etkinligi silinemedi: {raw}"

    parsed_ok, detail, event = _parse_deleted_event_payload(raw)
    if not parsed_ok:
        low = detail.lower()
        if "permission" in low or "mach error 4099" in low:
            return _calendar_permission_message()
        return f"Takvim etkinligi silinemedi: {detail}"

    assert event is not None
    now = dt.datetime.now()
    line = _format_event_line(event, now)
    return f"Takvimden silindi: {line}."
