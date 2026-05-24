from pathlib import Path
from datetime import datetime
import json
import uuid


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

MEMORY_FILE = DATA_DIR / "agent_memory.json"


DEFAULT_MEMORY = {
    "job_preferences": [],
    "company_feedback": [],
    "role_feedback": [],
    "job_feedback": []
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def make_id(prefix):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{prefix}_{timestamp}_{short_id}"


def load_memory():
    if not MEMORY_FILE.exists():
        save_memory(DEFAULT_MEMORY)
        return DEFAULT_MEMORY.copy()

    with open(MEMORY_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Make sure new categories exist if added later.
    for key, value in DEFAULT_MEMORY.items():
        if key not in data:
            data[key] = value

    return data


def save_memory(memory):
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

    return "\n".join(sections)