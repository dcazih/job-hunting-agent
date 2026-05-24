from pathlib import Path
from datetime import datetime
import json


DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

SEEN_JOBS_FILE = DATA_DIR / "seen_jobs.json"
RUN_STATE_FILE = DATA_DIR / "last_successful_report_date.txt"


def load_seen_job_ids():
    if not SEEN_JOBS_FILE.exists():
        return set()

    with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    return set(data)


def save_seen_job_ids(job_ids):
    existing = load_seen_job_ids()
    updated = existing.union(set(job_ids))

    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(list(updated)), file, indent=2)


def already_sent_today():
    today = datetime.now().strftime("%Y-%m-%d")

    if not RUN_STATE_FILE.exists():
        return False

    last_date = RUN_STATE_FILE.read_text(encoding="utf-8").strip()
    return last_date == today


def mark_sent_today():
    today = datetime.now().strftime("%Y-%m-%d")
    RUN_STATE_FILE.write_text(today, encoding="utf-8")


def save_report(report_text):
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