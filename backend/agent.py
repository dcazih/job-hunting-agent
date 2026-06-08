from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
import contextvars
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import pymupdf

from job_tools.emailer import send_email
from job_tools.job_scorer import score_jobs
from job_tools.linkedin_scraper import scrape_jobs
from job_tools.memory_store import add_job_feedback, memory_as_text
from job_tools.resume_loader import (
    DEFAULT_PREFERENCES,
    DEFAULT_RESUME_PDF,
    DEFAULT_RESUME_TXT,
    load_candidate_profile,
    refresh_resume_text_from_pdf,
    store_resume_text,
)
from job_tools.storage import (
    load_latest_report,
    mark_sent_today,
    save_report,
    save_seen_job_ids,
    load_seen_job_ids,
)
from job_tools.cloud_state import (
    enabled as cloud_enabled,
    set_json as cloud_set_json,
    get_json as cloud_get_json,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.getenv("APP_RUNTIME_DIR", "/tmp/job-hunting-agent" if os.getenv("VERCEL") else str(ROOT_DIR)))
DATA_DIR = RUNTIME_ROOT / "data"
REPORTS_DIR = RUNTIME_ROOT / "reports"
PROFILE_DIR = RUNTIME_ROOT / "profile"
UPLOADS_DIR = RUNTIME_ROOT / "uploads"
UPLOAD_THUMBNAILS_DIR = UPLOADS_DIR / "thumbnails"
RESUME_STATE_PATH = DATA_DIR / "resume_state.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SearchProgress:
    run_id: str
    status: str
    progress: int
    step: str
    started_at: str
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


SEARCH_RUNS: dict[str, SearchProgress] = {}
RUNS_LOCK = threading.Lock()
CANCEL_REQUESTS: set[str] = set()
CHAT_AGENT_RUN_ID = "chat-agent"
CHAT_SESSION_ACTIVE_RUNS: dict[str, str] = {}
CHAT_SESSION_MESSAGES: dict[str, list[dict[str, Any]]] = {}
CHAT_SESSION_LOCKS: dict[str, threading.RLock] = {}
CHAT_SESSION_LOCKS_LOCK = threading.Lock()
CHAT_SESSION_RUNS_LOCK = threading.Lock()
CURRENT_RUN_ID: contextvars.ContextVar[str] = contextvars.ContextVar("current_run_id", default="")
CURRENT_RESUME_DISPLAY_NAME: contextvars.ContextVar[str] = contextvars.ContextVar("current_resume_display_name", default="")
CURRENT_TIME_ZONE: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_time_zone",
    default=os.getenv("APP_DEFAULT_TIMEZONE", "UTC").strip() or "UTC",
)
SCHEDULE_LOCK = threading.Lock()
SCHEDULE_PATH = DATA_DIR / "schedule_config.json"
SCHEDULER_THREAD: threading.Thread | None = None
SCHEDULER_STOP = threading.Event()
SCHEDULE_DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_TIMEZONE = os.getenv("APP_DEFAULT_TIMEZONE", "UTC").strip() or "UTC"
DEFAULT_SCHEDULE: dict[str, Any] = {
    "enabled": False,
    "time": "09:00",
    "timezone": DEFAULT_TIMEZONE,
    "days": {day: day in {"mon", "tue", "wed", "thu", "fri"} for day in SCHEDULE_DAY_KEYS},
    "keywords": "software engineer",
    "location": "United States",
    "pages": 2,
    "email_to": "",
    "last_triggered_slot": "",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_timezone(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_TIMEZONE
    try:
        ZoneInfo(raw)
    except Exception:
        return DEFAULT_TIMEZONE
    return raw


def _schedule_zone(schedule: dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(_normalize_timezone(schedule.get("timezone", DEFAULT_SCHEDULE["timezone"])))


def _now_in_timezone(timezone_name: str | None = None) -> datetime:
    normalized = _normalize_timezone(timezone_name or get_current_time_zone())
    try:
        return datetime.now(ZoneInfo(normalized))
    except Exception:
        return datetime.now()


def _normalize_days(days: Any) -> dict[str, bool]:
    normalized = {day: False for day in SCHEDULE_DAY_KEYS}
    if isinstance(days, dict):
        for day in SCHEDULE_DAY_KEYS:
            normalized[day] = bool(days.get(day, False))
    return normalized


def _normalize_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", raw):
        return DEFAULT_SCHEDULE["time"]
    return raw


def _normalize_schedule(payload: Any, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(DEFAULT_SCHEDULE)
    if previous:
        base.update(previous)
        base["days"] = _normalize_days(previous.get("days", {}))

    if isinstance(payload, dict):
        if "enabled" in payload:
            base["enabled"] = bool(payload.get("enabled"))
        if "time" in payload:
            base["time"] = _normalize_time(payload.get("time"))
        if "timezone" in payload:
            base["timezone"] = _normalize_timezone(payload.get("timezone"))
        if "days" in payload:
            base["days"] = _normalize_days(payload.get("days"))
        if "keywords" in payload:
            base["keywords"] = str(payload.get("keywords") or "").strip() or DEFAULT_SCHEDULE["keywords"]
        if "location" in payload:
            base["location"] = str(payload.get("location") or "").strip() or DEFAULT_SCHEDULE["location"]
        if "pages" in payload:
            try:
                pages = int(payload.get("pages"))
            except (TypeError, ValueError):
                pages = DEFAULT_SCHEDULE["pages"]
            base["pages"] = max(1, min(10, pages))
        if "email_to" in payload:
            base["email_to"] = str(payload.get("email_to") or "").strip()
        if "last_triggered_slot" in payload:
            base["last_triggered_slot"] = str(payload.get("last_triggered_slot") or "").strip()

    if not any(base["days"].values()):
        base["enabled"] = False
    return base


def _get_stored_schedule() -> dict[str, Any]:
    if cloud_enabled():
        stored = cloud_get_json("scheduler.config", None)
        return _normalize_schedule(stored, None)

    if not SCHEDULE_PATH.exists():
        schedule = _normalize_schedule({}, None)
        SCHEDULE_PATH.write_text(json.dumps(schedule, indent=2), encoding="utf-8")
        return schedule

    try:
        stored = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        stored = {}
    schedule = _normalize_schedule(stored, None)
    SCHEDULE_PATH.write_text(json.dumps(schedule, indent=2), encoding="utf-8")
    return schedule


def _save_stored_schedule(schedule: dict[str, Any]) -> None:
    if cloud_enabled():
        cloud_set_json("scheduler.config", schedule)
        return
    SCHEDULE_PATH.write_text(json.dumps(schedule, indent=2), encoding="utf-8")


def _public_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(schedule.get("enabled", False)),
        "time": _normalize_time(schedule.get("time", DEFAULT_SCHEDULE["time"])),
        "timezone": _normalize_timezone(schedule.get("timezone", DEFAULT_SCHEDULE["timezone"])),
        "days": _normalize_days(schedule.get("days", {})),
        "keywords": str(schedule.get("keywords", DEFAULT_SCHEDULE["keywords"])),
        "location": str(schedule.get("location", DEFAULT_SCHEDULE["location"])),
        "pages": int(schedule.get("pages", DEFAULT_SCHEDULE["pages"])),
        "email_to": str(schedule.get("email_to", DEFAULT_SCHEDULE["email_to"])),
    }


def get_search_schedule() -> dict[str, Any]:
    with SCHEDULE_LOCK:
        schedule = _get_stored_schedule()
        return _public_schedule(schedule)


def save_search_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    with SCHEDULE_LOCK:
        current = _get_stored_schedule()
        schedule = _normalize_schedule(payload, current)
        _save_stored_schedule(schedule)
        return _public_schedule(schedule)


def get_current_run_id() -> str:
    return CURRENT_RUN_ID.get()


def set_current_run_id(run_id: str) -> None:
    CURRENT_RUN_ID.set(run_id)


def clear_current_run_id() -> None:
    CURRENT_RUN_ID.set("")


def get_current_resume_display_name() -> str:
    return str(CURRENT_RESUME_DISPLAY_NAME.get() or "").strip()


def set_current_resume_display_name(display_name: str) -> None:
    CURRENT_RESUME_DISPLAY_NAME.set(str(display_name or "").strip())


def clear_current_resume_display_name() -> None:
    CURRENT_RESUME_DISPLAY_NAME.set("")


def get_current_time_zone() -> str:
    return _normalize_timezone(CURRENT_TIME_ZONE.get())


def set_current_time_zone(timezone_name: str) -> None:
    CURRENT_TIME_ZONE.set(_normalize_timezone(timezone_name))


def clear_current_time_zone() -> None:
    CURRENT_TIME_ZONE.set(DEFAULT_TIMEZONE)


def get_chat_session_lock(session_id: str) -> threading.RLock:
    normalized = str(session_id or "default").strip() or "default"
    with CHAT_SESSION_LOCKS_LOCK:
        lock = CHAT_SESSION_LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            CHAT_SESSION_LOCKS[normalized] = lock
        return lock


def get_chat_messages(session_id: str) -> list[dict[str, Any]]:
    normalized = str(session_id or "default").strip() or "default"
    with get_chat_session_lock(normalized):
        return [dict(message) for message in CHAT_SESSION_MESSAGES.get(normalized, [])]


def save_chat_messages(session_id: str, messages: list[dict[str, Any]]) -> None:
    normalized = str(session_id or "default").strip() or "default"
    with get_chat_session_lock(normalized):
        CHAT_SESSION_MESSAGES[normalized] = [dict(message) for message in messages]


def clear_chat_messages(session_id: str) -> None:
    normalized = str(session_id or "default").strip() or "default"
    with get_chat_session_lock(normalized):
        CHAT_SESSION_MESSAGES.pop(normalized, None)


def get_chat_active_run_id(session_id: str) -> str:
    normalized = str(session_id or "default").strip() or "default"
    with CHAT_SESSION_RUNS_LOCK:
        return CHAT_SESSION_ACTIVE_RUNS.get(normalized, "")


def set_chat_active_run_id(session_id: str, run_id: str) -> None:
    normalized = str(session_id or "default").strip() or "default"
    with CHAT_SESSION_RUNS_LOCK:
        CHAT_SESSION_ACTIVE_RUNS[normalized] = str(run_id or "").strip()


def clear_chat_active_run_id(session_id: str) -> None:
    normalized = str(session_id or "default").strip() or "default"
    with CHAT_SESSION_RUNS_LOCK:
        CHAT_SESSION_ACTIVE_RUNS.pop(normalized, None)


def clear_search_run_cancel(run_id: str) -> None:
    if cloud_enabled():
        cloud_set_json(_run_cancel_key(run_id), False)
        return
    with RUNS_LOCK:
        CANCEL_REQUESTS.discard(run_id)


def is_search_run_canceled(run_id: str) -> bool:
    return _is_canceled(run_id)


def set_search_run_progress(
    run_id: str,
    *,
    status: str,
    progress: int,
    step: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    _set_progress(run_id, status=status, progress=progress, step=step, result=result, error=error)
    payload = get_search_run(run_id)
    return payload or {
        "run_id": run_id,
        "status": status,
        "progress": progress,
        "step": step,
        "result": result,
        "error": error,
    }


def _has_active_run() -> bool:
    with RUNS_LOCK:
        for run in SEARCH_RUNS.values():
            if run.status in {"queued", "running"}:
                return True
    return False


def _run_scheduled_search(schedule: dict[str, Any]) -> None:
    timezone_name = _normalize_timezone(schedule.get("timezone", DEFAULT_SCHEDULE["timezone"]))
    set_current_time_zone(timezone_name)
    try:
        run_id = create_search_run()
        execute_search_run(
            run_id,
            keywords=schedule.get("keywords", DEFAULT_SCHEDULE["keywords"]),
            location=schedule.get("location", DEFAULT_SCHEDULE["location"]),
            pages=int(schedule.get("pages", DEFAULT_SCHEDULE["pages"])),
            send_email_after=True,
            auto_email_to=str(schedule.get("email_to", "") or "").strip(),
        )
        return run_id
    finally:
        clear_current_time_zone()


def _scheduler_loop() -> None:
    while not SCHEDULER_STOP.is_set():
        try:
            with SCHEDULE_LOCK:
                schedule = _get_stored_schedule()
                if not schedule.get("enabled"):
                    pass
                else:
                    now = datetime.now(_schedule_zone(schedule))
                    day_key = SCHEDULE_DAY_KEYS[now.weekday()]
                    slot = now.strftime("%Y-%m-%d %H:%M")
                    if (
                        schedule.get("days", {}).get(day_key, False)
                        and now.strftime("%H:%M") == schedule.get("time")
                        and schedule.get("last_triggered_slot") != slot
                    ):
                        schedule["last_triggered_slot"] = slot
                        _save_stored_schedule(schedule)
                        if not _has_active_run():
                            worker = threading.Thread(
                                target=_run_scheduled_search,
                                args=(schedule,),
                                daemon=True,
                            )
                            worker.start()
        except Exception:
            # Keep scheduler alive even if one cycle fails.
            pass
        time.sleep(20)


def start_scheduler() -> None:
    global SCHEDULER_THREAD
    with SCHEDULE_LOCK:
        if SCHEDULER_THREAD and SCHEDULER_THREAD.is_alive():
            return
        SCHEDULER_STOP.clear()
        SCHEDULER_THREAD = threading.Thread(target=_scheduler_loop, daemon=True)
        SCHEDULER_THREAD.start()


def stop_scheduler() -> None:
    SCHEDULER_STOP.set()


def run_daily_schedule_cron() -> dict[str, Any]:
    with SCHEDULE_LOCK:
        schedule = _get_stored_schedule()
        if not schedule.get("enabled"):
            return {"status": "skipped", "reason": "disabled"}

        now = datetime.now(_schedule_zone(schedule))
        day_key = SCHEDULE_DAY_KEYS[now.weekday()]
        if not schedule.get("days", {}).get(day_key, False):
            return {"status": "skipped", "reason": "day_disabled"}

        if _has_active_run():
            return {"status": "skipped", "reason": "active_run"}

        slot = now.strftime("%Y-%m-%d %H:%M")
        if schedule.get("last_triggered_slot") == slot:
            return {"status": "skipped", "reason": "already_triggered"}

        schedule["last_triggered_slot"] = slot
        _save_stored_schedule(schedule)

    worker = threading.Thread(target=_run_scheduled_search, args=(schedule,), daemon=True)
    worker.start()
    return {"status": "started", "keywords": schedule.get("keywords", DEFAULT_SCHEDULE["keywords"]), "location": schedule.get("location", DEFAULT_SCHEDULE["location"]), "pages": int(schedule.get("pages", DEFAULT_SCHEDULE["pages"]))}


def _run_progress_key(run_id: str) -> str:
    return f"runs.progress.{run_id}"


def _run_cancel_key(run_id: str) -> str:
    return f"runs.cancel.{run_id}"


def _set_progress(run_id: str, *, status: str, progress: int, step: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    completed_at: str | None = None
    with RUNS_LOCK:
        existing = SEARCH_RUNS.get(run_id)
        if existing is None:
            existing = SearchProgress(
                run_id=run_id,
                status="queued",
                progress=0,
                step="Queued",
                started_at=_now_iso(),
            )
            SEARCH_RUNS[run_id] = existing
        existing.status = status
        existing.progress = progress
        existing.step = step
        existing.result = result
        existing.error = error
        if status in {"complete", "failed"}:
            existing.completed_at = _now_iso()
        completed_at = existing.completed_at
        started_at = existing.started_at

    if cloud_enabled():
        cloud_set_json(
            _run_progress_key(run_id),
            {
                "run_id": run_id,
                "status": status,
                "progress": progress,
                "step": step,
                "started_at": started_at,
                "completed_at": completed_at,
                "result": result,
                "error": error,
            },
        )


def _is_canceled(run_id: str) -> bool:
    if cloud_enabled():
        return bool(cloud_get_json(_run_cancel_key(run_id), False))
    with RUNS_LOCK:
        return run_id in CANCEL_REQUESTS


def cancel_search_run(run_id: str) -> dict[str, Any]:
    if cloud_enabled():
        run = cloud_get_json(_run_progress_key(run_id), None)
        if not run:
            raise ValueError("Run not found")
        cloud_set_json(_run_cancel_key(run_id), True)
        _set_progress(run_id, status="failed", progress=100, step="Canceled", error="Search was canceled by user.")
        return {"status": "cancel_requested", "run_id": run_id}

    with RUNS_LOCK:
        run = SEARCH_RUNS.get(run_id)
        if run is None:
            raise ValueError("Run not found")
        CANCEL_REQUESTS.add(run_id)
    _set_progress(run_id, status="failed", progress=100, step="Canceled", error="Search was canceled by user.")
    return {"status": "cancel_requested", "run_id": run_id}


def _guard_canceled(run_id: str) -> None:
    if _is_canceled(run_id):
        _set_progress(run_id, status="failed", progress=100, step="Canceled", error="Search was canceled by user.")
        raise RuntimeError("Search was canceled by user.")


def create_search_run() -> str:
    run_id = uuid.uuid4().hex
    started_at = _now_iso()
    with RUNS_LOCK:
        SEARCH_RUNS[run_id] = SearchProgress(
            run_id=run_id,
            status="queued",
            progress=0,
            step="Queued",
            started_at=started_at,
        )
    if cloud_enabled():
        cloud_set_json(
            _run_progress_key(run_id),
            {
                "run_id": run_id,
                "status": "queued",
                "progress": 0,
                "step": "Queued",
                "started_at": started_at,
                "completed_at": None,
                "result": None,
                "error": None,
            },
        )
        cloud_set_json(_run_cancel_key(run_id), False)
    return run_id


def get_search_run(run_id: str) -> dict[str, Any] | None:
    if cloud_enabled():
        run = cloud_get_json(_run_progress_key(run_id), None)
        if run is None:
            return None
        return run
    with RUNS_LOCK:
        run = SEARCH_RUNS.get(run_id)
        return asdict(run) if run else None


def _thumbnail_path_for_upload(upload_name: str) -> Path:
    return UPLOAD_THUMBNAILS_DIR / f"{Path(upload_name).stem}.png"


def _ensure_resume_thumbnail(pdf_path: Path) -> Path | None:
    if not pdf_path.exists():
        return None
    thumbnail_path = _thumbnail_path_for_upload(pdf_path.name)
    # Re-render if missing or older than source PDF.
    if thumbnail_path.exists() and thumbnail_path.stat().st_mtime >= pdf_path.stat().st_mtime:
        return thumbnail_path

    doc = pymupdf.open(pdf_path)
    try:
        if doc.page_count == 0:
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(0.35, 0.35), alpha=False)
        pix.save(thumbnail_path)
        return thumbnail_path
    finally:
        doc.close()


def save_uploaded_resume(file_name: str, content: bytes) -> dict[str, Any]:
    if not file_name.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{Path(file_name).name}"
    upload_path = UPLOADS_DIR / safe_name

    upload_path.write_bytes(content)
    _ensure_resume_thumbnail(upload_path)

    # Canonical active resume location used by current agent/profile loader.
    shutil.copy(upload_path, DEFAULT_RESUME_PDF)
    RESUME_STATE_PATH.write_text(json.dumps({"active_upload_name": safe_name}), encoding="utf-8")

    extracted = refresh_resume_text_from_pdf()

    return {
        "status": "uploaded",
        "upload_path": str(upload_path),
        "active_resume_path": str(DEFAULT_RESUME_PDF),
        "upload_name": safe_name,
        "characters_extracted": len(extracted),
    }


def save_preferences(preferences: str) -> dict[str, Any]:
    text = preferences.strip()
    if not text:
        raise ValueError("Preferences text cannot be empty.")

    if cloud_enabled():
        cloud_set_json("profile.preferences", text)
    else:
        DEFAULT_PREFERENCES.write_text(text, encoding="utf-8")

    return {
        "status": "saved",
        "preferences_path": str(DEFAULT_PREFERENCES),
        "characters": len(text),
    }


def get_preferences() -> dict[str, Any]:
    if cloud_enabled():
        text = str(cloud_get_json("profile.preferences", "") or "")
        return {"found": bool(text.strip()), "preferences": text}
    if not DEFAULT_PREFERENCES.exists():
        return {"found": False, "preferences": ""}

    return {
        "found": True,
        "preferences": DEFAULT_PREFERENCES.read_text(encoding="utf-8"),
    }


def get_resume_status() -> dict[str, Any]:
    cached_resume_text = ""
    if cloud_enabled():
        cached_resume_text = str(cloud_get_json("profile.resume_text", "") or "").strip()
    return {
        "found": DEFAULT_RESUME_PDF.exists() or bool(cached_resume_text),
        "resume_path": str(DEFAULT_RESUME_PDF),
    }


def _load_active_upload_name() -> str:
    if cloud_enabled():
        return str(cloud_get_json("resume.active_upload_name", "") or "").strip()
    if not RESUME_STATE_PATH.exists():
        return ""
    try:
        payload = json.loads(RESUME_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str(payload.get("active_upload_name", "")).strip()


def _set_active_upload_name(name: str) -> None:
    if cloud_enabled():
        cloud_set_json("resume.active_upload_name", name)
        return
    RESUME_STATE_PATH.write_text(json.dumps({"active_upload_name": name}), encoding="utf-8")


def list_uploaded_resumes() -> dict[str, Any]:
    active_upload_name = _load_active_upload_name()
    uploads = sorted(UPLOADS_DIR.glob("*.pdf"), key=lambda path: path.stat().st_mtime)
    if uploads and active_upload_name not in {item.name for item in uploads}:
        # Ensure there is always one selected resume when uploads exist.
        active_upload_name = uploads[0].name
        _set_active_upload_name(active_upload_name)
        shutil.copy(uploads[0], DEFAULT_RESUME_PDF)
        refresh_resume_text_from_pdf()

    items = []
    for item in uploads:
        thumb = _ensure_resume_thumbnail(item)
        thumb_url = f"/api/resume/uploads/{item.name}/thumbnail" if thumb else None
        items.append(
            {
                "name": item.name,
                "display_name": item.name.split("_", 1)[1] if "_" in item.name else item.name,
                "is_active": item.name == active_upload_name,
                "thumbnail_url": thumb_url,
            }
        )
    return {"resumes": items}


def delete_uploaded_resume(upload_name: str) -> dict[str, Any]:
    safe_name = Path(upload_name).name
    target = UPLOADS_DIR / safe_name
    if not target.exists():
        raise ValueError("Resume upload not found.")
    thumb_path = _thumbnail_path_for_upload(safe_name)
    if thumb_path.exists():
        thumb_path.unlink()

    active_upload_name = _load_active_upload_name()
    deleting_active = safe_name == active_upload_name
    target.unlink()

    remaining = sorted(UPLOADS_DIR.glob("*.pdf"), key=lambda path: path.stat().st_mtime, reverse=True)
    new_active = ""

    if deleting_active:
        if remaining:
            fallback = remaining[0]
            shutil.copy(fallback, DEFAULT_RESUME_PDF)
            refresh_resume_text_from_pdf()
            new_active = fallback.name
        else:
            if DEFAULT_RESUME_PDF.exists():
                DEFAULT_RESUME_PDF.unlink()
            if DEFAULT_RESUME_TXT.exists():
                DEFAULT_RESUME_TXT.unlink()
            store_resume_text("")
    else:
        new_active = active_upload_name

    _set_active_upload_name(new_active)

    return {
        "status": "deleted",
        "deleted_upload_name": safe_name,
        "active_upload_name": new_active,
        "remaining": len(remaining),
    }


def set_active_uploaded_resume(upload_name: str) -> dict[str, Any]:
    safe_name = Path(upload_name).name
    target = UPLOADS_DIR / safe_name
    if not target.exists():
        raise ValueError("Resume upload not found.")
    _ensure_resume_thumbnail(target)

    shutil.copy(target, DEFAULT_RESUME_PDF)
    refresh_resume_text_from_pdf()
    _set_active_upload_name(safe_name)

    return {
        "status": "selected",
        "active_upload_name": safe_name,
        "active_resume_path": str(DEFAULT_RESUME_PDF),
    }


def _list_md(items: list[Any]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def _job_block(job: dict[str, Any], rank: int | None = None) -> str:
    rank_text = f"#{rank} " if rank is not None else ""

    return f"""
## {rank_text}{job.get("title")} - {job.get("company")}

**Score:** {job.get("score")}/100  
**Recommendation:** {job.get("recommendation")}  
**Location:** {job.get("location")}  
**Listed at:** {job.get("listed_at")}  
**Link:** {job.get("url")}

**Fit summary:**  
{job.get("fit_summary")}

**Why it matches:**  
{_list_md(job.get("match_reasons", []))}

**Concerns:**  
{_list_md(job.get("concerns", []))}

**Matched skills:**  
{_list_md(job.get("matched_skills", []))}

**Missing / weak skills:**  
{_list_md(job.get("missing_or_weak_skills", []))}

---
""".strip()


def _extract_report_role(keywords: str, top_jobs: list[dict[str, Any]]) -> str:
    text = (keywords or "").strip()
    lower = text.lower()

    prefixes = [
        "start search",
        "start hunt",
        "find jobs",
        "get jobs",
        "search",
        "hunt",
        "find",
        "run",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            text = text[len(prefix):].strip(" :,-")
            lower = text.lower()
            break

    separators = [" in ", " near ", " around ", " at "]
    for sep in separators:
        idx = lower.find(sep)
        if idx > 0:
            text = text[:idx].strip(" ,:-")
            break

    if not text:
        text = str((top_jobs[0] if top_jobs else {}).get("title", "")).strip()

    text = " ".join(text.split())
    return text[:70] if text else "Job Search"


def _report_display_name(role: str) -> str:
    now = _now_in_timezone()
    date_text = now.strftime("%b %d, %Y").replace(" 0", " ")
    return f"{role} · {date_text}"


def _build_report(scored_jobs: list[dict[str, Any]], keywords: str) -> dict[str, Any]:
    today = _now_in_timezone().strftime("%Y-%m-%d")

    ordered_jobs = sorted(scored_jobs, key=lambda item: item.get("score", 0), reverse=True)
    top_5 = ordered_jobs[:5]
    rest = ordered_jobs[5:]

    top_5_text = "\n\n".join(_job_block(job, rank=index) for index, job in enumerate(top_5, start=1))
    rest_text = "\n\n".join(_job_block(job) for job in rest)

    if not top_5_text:
        top_5_text = "No strong matches found."
    if not rest_text:
        rest_text = "No additional jobs found."

    report_md = f"""
# Daily Software Engineering Job Report - {today}

Found and scored **{len(ordered_jobs)}** fresh jobs.

# Top 5 Best Matches

{top_5_text}

# Remaining Jobs

{rest_text}
""".strip()

    role = _extract_report_role(keywords, top_5)
    report_name = _report_display_name(role)
    report_path = save_report(report_md, report_name=report_name)

    payload = {
        "status": "complete",
        "report_path": report_path,
        "target_industry": role,
        "report": report_md,
        "top_jobs": top_5,
        "remaining_jobs": rest,
        "job_count": len(ordered_jobs),
    }

    latest_run_path = DATA_DIR / "latest_run.json"
    latest_run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Keep searchable JSON snapshots alongside markdown reports.
    latest_report_path = Path(report_path)
    snapshot_path = REPORTS_DIR / f"{latest_report_path.stem}.json"
    snapshot_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return payload


def execute_search_run(
    run_id: str,
    *,
    keywords: str,
    location: str,
    pages: int,
    send_email_after: bool = False,
    auto_email_to: str = "",
) -> None:
    try:
        _guard_canceled(run_id)
        _set_progress(run_id, status="running", progress=10, step="Loading profile")
        profile = load_candidate_profile()

        _guard_canceled(run_id)
        _set_progress(run_id, status="running", progress=20, step="Loading memory")
        memory_text = memory_as_text()

        _guard_canceled(run_id)
        _set_progress(run_id, status="running", progress=35, step="Scraping jobs")
        jobs = scrape_jobs(
            keywords=keywords,
            location=location,
            pages=pages,
            is_canceled=lambda: _is_canceled(run_id),
        )

        _guard_canceled(run_id)
        _set_progress(run_id, status="running", progress=55, step="Filtering seen jobs")
        seen = load_seen_job_ids()
        fresh_jobs = [job for job in jobs if (job.get("job_id") or job.get("url")) not in seen]

        _guard_canceled(run_id)
        _set_progress(run_id, status="running", progress=70, step="Scoring jobs")
        scored_jobs = score_jobs(
            jobs=fresh_jobs,
            resume_text=profile["resume_text"],
            preferences_text=profile["preferences_text"] + "\n\nSaved memory:\n" + memory_text,
            is_canceled=lambda: _is_canceled(run_id),
        )

        _guard_canceled(run_id)
        _set_progress(run_id, status="running", progress=90, step="Building report")
        result = _build_report(scored_jobs, keywords)

        _guard_canceled(run_id)
        save_seen_job_ids([job.get("job_id") or job.get("url") for job in scored_jobs if (job.get("job_id") or job.get("url"))])
        mark_sent_today()

        if send_email_after:
            _guard_canceled(run_id)
            _set_progress(run_id, status="running", progress=95, step="Sending email")
            subject = f"Scheduled SWE Job Report - {_now_in_timezone().strftime('%Y-%m-%d')}"
            email_result = send_email(
                subject=subject,
                body=result.get("report", ""),
                to_email=auto_email_to,
            )
            result["email_result"] = email_result

        _set_progress(run_id, status="complete", progress=100, step="Completed", result=result)

    except Exception as error:
        if not _is_canceled(run_id):
            _set_progress(run_id, status="failed", progress=100, step="Failed", error=str(error))
    finally:
        if cloud_enabled():
            cloud_set_json(_run_cancel_key(run_id), False)
        with RUNS_LOCK:
            CANCEL_REQUESTS.discard(run_id)


def get_latest_report() -> dict[str, Any]:
    latest_report = load_latest_report()
    if not latest_report["found"]:
        return {
            "found": False,
            "report_path": None,
            "report": None,
            "top_jobs": [],
            "remaining_jobs": [],
        }

    report_path = Path(latest_report["report_path"])
    snapshot_path = REPORTS_DIR / f"{report_path.stem}.json"

    top_jobs: list[dict[str, Any]] = []
    remaining_jobs: list[dict[str, Any]] = []
    target_industry = ""

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        top_jobs = snapshot.get("top_jobs", [])
        remaining_jobs = snapshot.get("remaining_jobs", [])
        target_industry = str(snapshot.get("target_industry", "") or "")

    return {
        "found": True,
        "report_path": latest_report["report_path"],
        "report_name": report_path.name,
        "target_industry": target_industry,
        "report": latest_report["report"],
        "top_jobs": top_jobs,
        "remaining_jobs": remaining_jobs,
    }


def get_report_by_path(report_path: str) -> dict[str, Any]:
    requested_path = Path(report_path).resolve()
    reports_root = REPORTS_DIR.resolve()

    if reports_root not in requested_path.parents or requested_path.suffix != ".md":
        raise ValueError("Invalid report path.")

    if not requested_path.exists():
        raise FileNotFoundError("Report not found.")

    snapshot_path = REPORTS_DIR / f"{requested_path.stem}.json"

    top_jobs: list[dict[str, Any]] = []
    remaining_jobs: list[dict[str, Any]] = []
    target_industry = ""
    job_count = 0

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        top_jobs = snapshot.get("top_jobs", [])
        remaining_jobs = snapshot.get("remaining_jobs", [])
        target_industry = str(snapshot.get("target_industry", "") or "")
        job_count = snapshot.get("job_count", len(top_jobs) + len(remaining_jobs))
    else:
        job_count = 0

    return {
        "found": True,
        "report_path": str(requested_path),
        "report_name": requested_path.name,
        "target_industry": target_industry,
        "report": requested_path.read_text(encoding="utf-8"),
        "top_jobs": top_jobs,
        "remaining_jobs": remaining_jobs,
        "job_count": job_count,
    }


def list_reports() -> dict[str, Any]:
    entries = []
    for path in sorted(REPORTS_DIR.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        entries.append(
            {
                "report_path": str(path),
                "name": path.name,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )

    return {"reports": entries}


def delete_report_by_path(report_path: str) -> dict[str, Any]:
    requested_path = Path(report_path).resolve()
    reports_root = REPORTS_DIR.resolve()

    if reports_root not in requested_path.parents or requested_path.suffix != ".md":
        raise ValueError("Invalid report path.")

    if not requested_path.exists():
        raise FileNotFoundError("Report not found.")

    snapshot_path = REPORTS_DIR / f"{requested_path.stem}.json"
    deleted_snapshot = False

    requested_path.unlink()
    if snapshot_path.exists():
        snapshot_path.unlink()
        deleted_snapshot = True

    return {
        "status": "deleted",
        "report_path": str(requested_path),
        "deleted_snapshot": deleted_snapshot,
    }


def email_latest_report(to_email: str = "") -> dict[str, Any]:
    latest = load_latest_report()

    if not latest["found"]:
        return {
            "status": "failed",
            "message": "No saved report found.",
        }

    subject = f"Most Recent SWE Job Report - {_now_in_timezone().strftime('%Y-%m-%d')}"
    email_result = send_email(subject=subject, body=latest["report"], to_email=to_email)

    return {
        "status": "sent_existing_report" if email_result.get("status") == "sent" else "failed",
        "report_path": latest["report_path"],
        "email_result": email_result,
    }


def save_feedback(job_id: str, feedback: str, reason: str = "", title: str = "Unknown", company: str = "Unknown") -> dict[str, Any]:
    normalized_feedback = feedback.strip().lower()
    normalized_reason = reason.strip()

    memory_feedback = normalized_feedback if not normalized_reason else f"{normalized_feedback}: {normalized_reason}"

    item = add_job_feedback(
        job_id=job_id,
        title=title,
        company=company,
        feedback=memory_feedback,
    )

    return {
        "status": "saved",
        "item": item,
    }
