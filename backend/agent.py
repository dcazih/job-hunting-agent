from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import pymupdf

# Make current repo modules importable.
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from emailer import send_email
from job_scorer import score_jobs
from linkedin_scraper import scrape_jobs
from memory_store import add_job_feedback, memory_as_text
from resume_loader import DEFAULT_PREFERENCES, DEFAULT_RESUME_PDF, DEFAULT_RESUME_TXT, load_candidate_profile, refresh_resume_text_from_pdf
from storage import load_latest_report, mark_sent_today, save_report, save_seen_job_ids, load_seen_job_ids
from cloud_state import enabled as cloud_enabled, set_json as cloud_set_json, get_json as cloud_get_json


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


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
    return {
        "found": DEFAULT_RESUME_PDF.exists(),
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


def _build_report(scored_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")

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

    report_path = save_report(report_md)

    payload = {
        "status": "complete",
        "report_path": report_path,
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


def execute_search_run(run_id: str, *, keywords: str, location: str, pages: int) -> None:
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
        result = _build_report(scored_jobs)

        _guard_canceled(run_id)
        save_seen_job_ids([job.get("job_id") or job.get("url") for job in scored_jobs if (job.get("job_id") or job.get("url"))])
        mark_sent_today()

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

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        top_jobs = snapshot.get("top_jobs", [])
        remaining_jobs = snapshot.get("remaining_jobs", [])

    return {
        "found": True,
        "report_path": latest_report["report_path"],
        "report_name": report_path.name,
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
    job_count = 0

    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        top_jobs = snapshot.get("top_jobs", [])
        remaining_jobs = snapshot.get("remaining_jobs", [])
        job_count = snapshot.get("job_count", len(top_jobs) + len(remaining_jobs))
    else:
        job_count = 0

    return {
        "found": True,
        "report_path": str(requested_path),
        "report_name": requested_path.name,
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

    subject = f"Most Recent SWE Job Report - {datetime.now().strftime('%Y-%m-%d')}"
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
