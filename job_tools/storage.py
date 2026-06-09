from pathlib import Path
from datetime import datetime
import json
import os
import re
from typing import Any
from job_tools.cloud_state import enabled as cloud_enabled, get_json as cloud_get_json, set_json as cloud_set_json


ROOT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.getenv("APP_RUNTIME_DIR", "/tmp/job-hunting-agent" if os.getenv("VERCEL") else str(ROOT_DIR)))
DATA_DIR = RUNTIME_ROOT / "data"
REPORTS_DIR = RUNTIME_ROOT / "reports"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SEEN_JOBS_FILE = DATA_DIR / "seen_jobs.json"
RUN_STATE_FILE = DATA_DIR / "last_successful_report_date.txt"
REPORT_ENTRIES_KEY = "reports.entries"


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


def _cloud_report_entries() -> list[dict[str, Any]]:
    entries = cloud_get_json(REPORT_ENTRIES_KEY, []) if cloud_enabled() else []
    return [entry for entry in (entries or []) if isinstance(entry, dict)]


def _save_cloud_report_entries(entries: list[dict[str, Any]]) -> None:
    if cloud_enabled():
        cloud_set_json(REPORT_ENTRIES_KEY, entries)


def _markdown_field(block: str, label: str) -> str:
    match = re.search(
        rf"^\*\*{re.escape(label)}:\*\*\s*(.*?)(?=\n\*\*|\n---|\Z)",
        block,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _markdown_list(block: str, label: str) -> list[str]:
    value = _markdown_field(block, label)
    if not value or value == "- None":
        return []
    return [
        line[2:].strip()
        for line in value.splitlines()
        if line.strip().startswith("- ") and line[2:].strip() != "None"
    ]


def _parse_markdown_job_blocks(section: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    blocks = re.split(r"(?=^##\s+)", section, flags=re.MULTILINE)
    for block in blocks:
        heading = re.match(
            r"^##\s+(?:#\d+\s+)?(.+?)\s+(?:—|-)\s+(.+?)\s*$",
            block,
            flags=re.MULTILINE,
        )
        if not heading:
            continue

        score_text = _markdown_field(block, "Score").split("/", 1)[0].strip()
        try:
            score: int | float = float(score_text)
            if score.is_integer():
                score = int(score)
        except ValueError:
            score = 0

        recommendation = (
            _markdown_field(block, "Recommendation").strip().lower().replace(" ", "_")
        )
        jobs.append(
            {
                "title": heading.group(1).strip(),
                "company": heading.group(2).strip(),
                "score": score,
                "recommendation": recommendation,
                "location": _markdown_field(block, "Location"),
                "listed_at": _markdown_field(block, "Listed at"),
                "url": _markdown_field(block, "Link"),
                "fit_summary": _markdown_field(block, "Fit summary"),
                "match_reasons": _markdown_list(block, "Why it matches"),
                "concerns": _markdown_list(block, "Concerns"),
                "matched_skills": _markdown_list(block, "Matched skills"),
                "missing_or_weak_skills": _markdown_list(block, "Missing / weak skills"),
            }
        )
    return jobs


def recover_report_jobs(
    report_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = str(report_text or "")
    top_match = re.search(
        r"^# Top 5 Best Matches\s*(.*?)(?=^# Remaining Jobs\s*|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    remaining_match = re.search(
        r"^# Remaining Jobs\s*(.*)\Z",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    top_jobs = _parse_markdown_job_blocks(top_match.group(1)) if top_match else []
    remaining_jobs = (
        _parse_markdown_job_blocks(remaining_match.group(1)) if remaining_match else []
    )
    return top_jobs, remaining_jobs


def _cloud_unique_report_path(base_name: str, existing_entries: list[dict[str, Any]]) -> str:
    candidate = f"{base_name}.md"
    existing_paths = {str(entry.get("report_path", "") or "") for entry in existing_entries}
    if candidate not in existing_paths:
        return candidate
    index = 2
    while True:
        candidate = f"{base_name} ({index}).md"
        if candidate not in existing_paths:
            return candidate
        index += 1


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


def save_report(report_text, report_name: str | None = None, report_data: dict[str, Any] | None = None):
    cleaned_name = _sanitize_report_name(report_name or "")
    if cloud_enabled():
        entries = _cloud_report_entries()
        if cleaned_name:
            report_path = _cloud_unique_report_path(cleaned_name, entries)
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            report_path = f"daily_job_report_{timestamp}.md"

        entry = {
            "report_path": report_path,
            "name": Path(report_path).name,
            "modified_at": datetime.now().isoformat(timespec="seconds"),
            "report": report_text,
        }
        if report_data:
            entry.update(report_data)
        entries = [entry] + [existing for existing in entries if str(existing.get("report_path", "") or "") != report_path]
        _save_cloud_report_entries(entries)
        return report_path

    if cleaned_name:
        path = _unique_report_path(cleaned_name)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = REPORTS_DIR / f"daily_job_report_{timestamp}.md"

    with open(path, "w", encoding="utf-8") as file:
        file.write(report_text)

    if report_data:
        snapshot_path = REPORTS_DIR / f"{Path(path).stem}.json"
        snapshot_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    return str(path)


def list_saved_reports() -> list[dict[str, Any]]:
    if cloud_enabled():
        return _cloud_report_entries()

    entries = []
    for path in sorted(REPORTS_DIR.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        entries.append(
            {
                "report_path": str(path),
                "name": path.name,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
        )
    return entries


def get_saved_report_entry(report_path: str) -> dict[str, Any] | None:
    requested = str(report_path or "").strip()
    if not requested:
        return None

    if cloud_enabled():
        entries = _cloud_report_entries()
        for index, entry in enumerate(entries):
            if str(entry.get("report_path", "") or "") == requested:
                if not entry.get("top_jobs") and not entry.get("remaining_jobs"):
                    top_jobs, remaining_jobs = recover_report_jobs(
                        str(entry.get("report", "") or "")
                    )
                    if top_jobs or remaining_jobs:
                        entry = {
                            **entry,
                            "top_jobs": top_jobs,
                            "remaining_jobs": remaining_jobs,
                            "job_count": len(top_jobs) + len(remaining_jobs),
                        }
                        entries[index] = entry
                        _save_cloud_report_entries(entries)
                return entry
        return None

    requested_path = Path(requested).resolve()
    reports_root = REPORTS_DIR.resolve()
    if reports_root not in requested_path.parents or requested_path.suffix != ".md":
        return None
    if not requested_path.exists():
        return None

    snapshot_path = REPORTS_DIR / f"{requested_path.stem}.json"
    payload: dict[str, Any] = {
        "report_path": str(requested_path),
        "name": requested_path.name,
        "modified_at": datetime.fromtimestamp(requested_path.stat().st_mtime).isoformat(timespec="seconds"),
        "report": requested_path.read_text(encoding="utf-8"),
    }
    if snapshot_path.exists():
        try:
            payload.update(json.loads(snapshot_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return payload


def delete_saved_report_entry(report_path: str) -> bool:
    requested = str(report_path or "").strip()
    if not requested:
        return False

    if cloud_enabled():
        entries = _cloud_report_entries()
        updated = [entry for entry in entries if str(entry.get("report_path", "") or "") != requested]
        if len(updated) == len(entries):
            return False
        _save_cloud_report_entries(updated)
        return True

    requested_path = Path(requested).resolve()
    reports_root = REPORTS_DIR.resolve()
    if reports_root not in requested_path.parents or requested_path.suffix != ".md":
        return False
    if not requested_path.exists():
        return False

    requested_path.unlink()
    snapshot_path = REPORTS_DIR / f"{requested_path.stem}.json"
    if snapshot_path.exists():
        snapshot_path.unlink()
    return True

def get_latest_report_path():
    if cloud_enabled():
        entries = _cloud_report_entries()
        if not entries:
            return None
        return str(entries[0].get("report_path", "") or "") or None

    report_files = sorted(
        REPORTS_DIR.glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    if not report_files:
        return None

    return report_files[0]


def load_latest_report():
    if cloud_enabled():
        entries = _cloud_report_entries()
        if not entries:
            return {
                "found": False,
                "report_path": None,
                "report": None
            }
        latest = entries[0]
        return {
            "found": True,
            "report_path": latest.get("report_path"),
            "report": latest.get("report"),
            "report_name": latest.get("name"),
            "top_jobs": latest.get("top_jobs", []),
            "remaining_jobs": latest.get("remaining_jobs", []),
            "target_industry": latest.get("target_industry", ""),
            "job_count": latest.get("job_count", 0),
        }

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
