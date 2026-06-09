from pathlib import Path
from datetime import datetime
import json
import uuid
import os
from job_tools.cloud_state import enabled as cloud_enabled, get_json as cloud_get_json, set_json as cloud_set_json


ROOT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(os.getenv("APP_RUNTIME_DIR", "/tmp/job-hunting-agent" if os.getenv("VERCEL") else str(ROOT_DIR)))
DATA_DIR = RUNTIME_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_FILE = DATA_DIR / "agent_memory.json"


DEFAULT_MEMORY = {
    "job_preferences": [],
    "company_feedback": [],
    "role_feedback": [],
    "job_feedback": [],
    "search_history": [],
    "search_context": {
        "last_target_industry": "",
    },
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def make_id(prefix):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{prefix}_{timestamp}_{short_id}"


def load_memory():
    if cloud_enabled():
        data = cloud_get_json("memory.store", DEFAULT_MEMORY.copy()) or DEFAULT_MEMORY.copy()
        for key, value in DEFAULT_MEMORY.items():
            if key not in data:
                data[key] = value
        if not isinstance(data.get("search_context"), dict):
            data["search_context"] = DEFAULT_MEMORY["search_context"].copy()
        for key, value in DEFAULT_MEMORY["search_context"].items():
            if key not in data["search_context"]:
                data["search_context"][key] = value
        return data
    if not MEMORY_FILE.exists():
        save_memory(DEFAULT_MEMORY)
        return DEFAULT_MEMORY.copy()

    with open(MEMORY_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Make sure new categories exist if added later.
    for key, value in DEFAULT_MEMORY.items():
        if key not in data:
            data[key] = value
    if not isinstance(data.get("search_context"), dict):
        data["search_context"] = DEFAULT_MEMORY["search_context"].copy()
    for key, value in DEFAULT_MEMORY["search_context"].items():
        if key not in data["search_context"]:
            data["search_context"][key] = value

    return data


def save_memory(memory):
    if cloud_enabled():
        cloud_set_json("memory.store", memory)
        return
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(memory, file, indent=2)


def add_job_preference(text, source="user"):
    memory = load_memory()

    item = {
        "id": make_id("pref"),
        "text": text,
        "created_at": now_iso(),
        "source": source
    }

    memory["job_preferences"].append(item)
    save_memory(memory)

    return item


def add_company_feedback(company, feedback, source="user"):
    memory = load_memory()

    item = {
        "id": make_id("company"),
        "company": company,
        "feedback": feedback,
        "created_at": now_iso(),
        "source": source
    }

    memory["company_feedback"].append(item)
    save_memory(memory)

    return item


def add_role_feedback(role_or_keyword, feedback, source="user"):
    memory = load_memory()

    item = {
        "id": make_id("role"),
        "role_or_keyword": role_or_keyword,
        "feedback": feedback,
        "created_at": now_iso(),
        "source": source
    }

    memory["role_feedback"].append(item)
    save_memory(memory)

    return item


def add_job_feedback(job_id, title, company, feedback, source="user"):
    memory = load_memory()

    item = {
        "id": make_id("job"),
        "job_id": job_id,
        "title": title,
        "company": company,
        "feedback": feedback,
        "created_at": now_iso(),
        "source": source
    }

    memory["job_feedback"].append(item)
    save_memory(memory)

    return item


def add_search_history(
    *,
    run_id,
    target_industry,
    company="",
    job_level="",
    location,
    pages,
    status,
    scraped_count=0,
    fresh_count=0,
    scored_count=0,
    report_path="",
    report_name="",
    assistant_message="",
    cancelled=False,
    source="agent",
):
    memory = load_memory()

    item = {
        "id": make_id("search"),
        "run_id": run_id,
        "target_industry": target_industry,
        "company": company,
        "job_level": job_level,
        "location": location,
        "pages": int(pages),
        "status": status,
        "scraped_count": int(scraped_count),
        "fresh_count": int(fresh_count),
        "scored_count": int(scored_count),
        "report_path": report_path,
        "report_name": report_name,
        "assistant_message": assistant_message,
        "cancelled": bool(cancelled),
        "created_at": now_iso(),
        "source": source,
    }

    memory["search_history"].append(item)
    save_memory(memory)

    return item


def get_last_target_industry() -> str:
    memory = load_memory()
    return str(memory.get("search_context", {}).get("last_target_industry", "") or "").strip()


def set_last_target_industry(target_industry: str) -> str:
    memory = load_memory()
    industry = str(target_industry or "").strip()
    memory["search_context"]["last_target_industry"] = industry
    save_memory(memory)
    return industry


def delete_memory_item(memory_id):
    memory = load_memory()

    deleted = None

    for category, items in memory.items():
        remaining = []

        for item in items:
            if item.get("id") == memory_id:
                deleted = {
                    "category": category,
                    "item": item
                }
            else:
                remaining.append(item)

        memory[category] = remaining

    save_memory(memory)

    return deleted


def memory_as_text():
    memory = load_memory()

    sections = []

    sections.append("Job preferences:")
    for item in memory["job_preferences"]:
        sections.append(f"- [{item['id']}] {item['text']}")

    sections.append("\nCompany feedback:")
    for item in memory["company_feedback"]:
        sections.append(f"- [{item['id']}] {item['company']}: {item['feedback']}")

    sections.append("\nRole feedback:")
    for item in memory["role_feedback"]:
        sections.append(f"- [{item['id']}] {item['role_or_keyword']}: {item['feedback']}")

    sections.append("\nSpecific job feedback:")
    for item in memory["job_feedback"]:
        sections.append(
            f"- [{item['id']}] {item['title']} at {item['company']} "
            f"({item['job_id']}): {item['feedback']}"
        )

    sections.append("\nSearch history:")
    for item in memory["search_history"]:
        cancelled_text = "yes" if item.get("cancelled") else "no"
        report_name = item.get("report_name") or item.get("report_path") or ""
        assistant_message = item.get("assistant_message") or ""
        company = item.get("company", "")
        job_level = item.get("job_level", "")
        summary = (
            f"- [{item['id']}] {item.get('target_industry', '')}"
            f"{f' @ {company}' if company else ''}"
            f"{f' [{job_level}]' if job_level else ''}"
            f" in {item.get('location', '')} "
            f"pages={item.get('pages', 1)} status={item.get('status', '')} "
            f"scraped={item.get('scraped_count', 0)} fresh={item.get('fresh_count', 0)} "
            f"scored={item.get('scored_count', 0)} cancelled={cancelled_text}"
        )
        if report_name:
            summary += f" report={report_name}"
        if assistant_message:
            summary += f" note={assistant_message}"
        sections.append(summary)

    last_target_industry = str(memory.get("search_context", {}).get("last_target_industry", "") or "").strip()
    if last_target_industry:
        sections.append(f"\nSearch context:\n- Last target industry: {last_target_industry}")

    return "\n".join(sections)
