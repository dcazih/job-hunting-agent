from pathlib import Path
from datetime import datetime
import json
import os
from job_tools.cloud_state import enabled as cloud_enabled, get_json as cloud_get_json, set_json as cloud_set_json


ROOT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.getenv("APP_RUNTIME_DIR", "/tmp/job-hunting-agent" if os.getenv("VERCEL") else str(ROOT_DIR)))
DATA_DIR = RUNTIME_ROOT / "data"
REPORTS_DIR = RUNTIME_ROOT / "reports"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SEEN_JOBS_FILE = DATA_DIR / "seen_jobs.json"
RUN_STATE_FILE = DATA_DIR / "last_successful_report_date.txt"


def load_seen_job_ids():
    if cloud_enabled():
        payload = cloud_get_json("jobs.seen_ids", [])
        return set(payload or [])
    if not SEEN_JOBS_FILE.exists():
        return set()

    with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    return set(data)


def save_seen_job_ids(job_ids):
    if cloud_enabled():
        existing = set(cloud_get_json("jobs.seen_ids", []) or [])
        updated = sorted(list(existing.union(set(job_ids))))
        cloud_set_json("jobs.seen_ids", updated)
        return
    existing = load_seen_job_ids()
    updated = existing.union(set(job_ids))

    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(list(updated)), file, indent=2)


def remove_seen_job_ids(job_ids):
    ids_to_remove = set(job_ids or [])
    if not ids_to_remove:
        return
    if cloud_enabled():
        existing = set(cloud_get_json("jobs.seen_ids", []) or [])
        updated = sorted(list(existing.difference(ids_to_remove)))
        cloud_set_json("jobs.seen_ids", updated)
        return

    existing = load_seen_job_ids()
    updated = existing.difference(ids_to_remove)

    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(list(updated)), file, indent=2)


def already_sent_today():
    today = datetime.now().strftime("%Y-%m-%d")
    if cloud_enabled():
        last_date = str(cloud_get_json("reports.last_successful_date", "") or "").strip()
        return last_date == today

    if not RUN_STATE_FILE.exists():
        return False

    last_date = RUN_STATE_FILE.read_text(encoding="utf-8").strip()
    return last_date == today


def mark_sent_today():
    today = datetime.now().strftime("%Y-%m-%d")
    if cloud_enabled():
        cloud_set_json("reports.last_successful_date", today)
        return
    RUN_STATE_FILE.write_text(today, encoding="utf-8")


def _sanitize_report_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        cleaned = cleaned.replace(ch, " ")
    cleaned = " ".join(cleaned.split())
    return cleaned[:120].strip()


def _unique_report_path(base_name: str) -> Path:
    candidate = REPORTS_DIR / f"{base_name}.md"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = REPORTS_DIR / f"{base_name} ({index}).md"
        if not candidate.exists():
            return candidate
        index += 1


def save_report(report_text, report_name: str | None = None):
    cleaned_name = _sanitize_report_name(report_name or "")
    if cleaned_name:
        path = _unique_report_path(cleaned_name)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = REPORTS_DIR / f"daily_job_report_{timestamp}.md"

    with open(path, "w", encoding="utf-8") as file:
        file.write(report_text)

    return str(path)

def get_latest_report_path():
    report_files = sorted(
        REPORTS_DIR.glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    if not report_files:
        return None

    return report_files[0]


def load_latest_report():
    latest_path = get_latest_report_path()

    if latest_path is None:
        return {
            "found": False,
            "report_path": None,
            "report": None
        }

    return {
        "found": True,
        "report_path": str(latest_path),
        "report": latest_path.read_text(encoding="utf-8")
    }
