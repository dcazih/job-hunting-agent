from datetime import datetime
from typing import List, Dict, Any
import re
import json
from pathlib import Path

from langchain.tools import tool

from job_tools.resume_loader import (
    load_candidate_profile as load_profile_from_files,
    refresh_resume_text_from_pdf,
)
from job_tools.linkedin_scraper import scrape_jobs
from job_tools.job_scorer import score_jobs
from job_tools.storage import (
    load_seen_job_ids,
    save_seen_job_ids,
    already_sent_today,
    mark_sent_today,
    save_report,
    load_latest_report,
    REPORTS_DIR,
)
from job_tools.emailer import send_email
from job_tools.memory_store import memory_as_text
from backend.agent import (
    CHAT_AGENT_RUN_ID,
    clear_search_run_cancel,
    get_current_run_id,
    get_latest_report,
    get_search_schedule,
    is_search_run_canceled,
    save_search_schedule,
    get_preferences,
    save_preferences,
    list_reports,
    get_report_by_path,
    set_search_run_progress,
)


def _current_chat_run_id() -> str:
    run_id = str(get_current_run_id() or "").strip()
    return run_id or CHAT_AGENT_RUN_ID


def _tool_log(name: str) -> None:
    print(f"TOOL: {name}")


def _extract_report_role(keywords: str, top_jobs: List[Dict[str, Any]]) -> str:
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
            text = text[len(prefix) :].strip(" :,-")
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
    role_text = " ".join(str(role or "").split()).title()
    date_text = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")
    time_text = datetime.now().strftime("%I:%M %p").lstrip("0").lower()
    return f"{role_text} · {date_text} {time_text}"


@tool
def check_report_sent_today() -> dict:
    """Check whether today's job report has already been sent."""
    _tool_log("check_report_sent_today")
    return {"already_sent_today": already_sent_today()}


@tool
def load_candidate_profile() -> dict:
    """
    Load the candidate's resume and job preferences.
    Supports profile/resume.pdf and profile/resume.txt.
    Preferences are optional and may be empty.
    """

    _tool_log("load_candidate_profile")
    return load_profile_from_files()


@tool
def refresh_resume_from_pdf() -> dict:
    """
    Re-extract profile/resume.pdf into profile/resume.txt.
    Use this when the user updates or replaces their resume PDF.
    """

    _tool_log("refresh_resume_from_pdf")
    text = refresh_resume_text_from_pdf()

    return {
        "status": "refreshed",
        "characters_extracted": len(text),
        "preview": text[:1000],
    }


@tool
def scrape_linkedin_jobs_tool(
    keywords: str = "software engineer", location: str = "United States", pages: int = 1
) -> dict:
    """
    Scrape public LinkedIn guest job results for a keyword and location.
    Returns job cards with descriptions.
    """

    _tool_log("scrape_linkedin_jobs_tool")
    jobs = scrape_jobs(keywords=keywords, location=location, pages=pages)

    return {
        "keywords": keywords,
        "location": location,
        "pages": pages,
        "count": len(jobs),
        "jobs": jobs,
    }


@tool
def filter_seen_jobs(jobs: List[Dict[str, Any]]) -> dict:
    """Remove jobs that have already been reported in previous runs."""
    _tool_log("filter_seen_jobs")
    seen_ids = load_seen_job_ids()

    fresh_jobs = []

    for job in jobs:
        job_id = job.get("job_id") or job.get("url")

        if not job_id:
            continue

        if job_id in seen_ids:
            continue

        fresh_jobs.append(job)

    return {
        "original_count": len(jobs),
        "fresh_count": len(fresh_jobs),
        "fresh_jobs": fresh_jobs,
    }


@tool
def score_jobs_against_profile(
    jobs: List[Dict[str, Any]],
    resume_text: str,
    preferences_text: str = "",
    memory_text: str = "",
) -> dict:
    """Score jobs against the candidate's resume. Preferences and memory are optional."""
    _tool_log("score_jobs_against_profile")
    scored = score_jobs(
        jobs=jobs,
        resume_text=resume_text,
        preferences_text=(preferences_text or "").strip() + (
            f"\n\nSaved memory:\n{memory_text}" if str(memory_text or "").strip() else ""
        ),
    )

    return {
        "count": len(scored),
        "scored_jobs": scored,
    }


@tool
def build_daily_report(scored_jobs: List[Dict[str, Any]]) -> dict:
    """
    Build a Markdown daily job report.
    The report must show the top 5 jobs first, then the remaining jobs.
    """
    _tool_log("build_daily_report")

    target_industry = "software engineer"

    # Be robust to agent passing the full tool payload instead of only the list.
    if isinstance(scored_jobs, dict):
        target_industry = str(
            scored_jobs.get("target_industry")
            or scored_jobs.get("keywords")
            or target_industry
        ).strip() or target_industry
        scored_jobs = list(scored_jobs.get("scored_jobs", []) or [])
    if not isinstance(scored_jobs, list):
        scored_jobs = []

    display_target_industry = target_industry.strip() or "software engineer"
    report_role = _extract_report_role(display_target_industry, scored_jobs)
    report_title = _report_display_name(report_role)

    scored_jobs = sorted(
        scored_jobs, key=lambda item: item.get("score", 0), reverse=True
    )

    top_5 = scored_jobs[:5]
    rest = scored_jobs[5:]

    def list_md(items):
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items)

    def job_block(job, rank=None):
        rank_text = f"#{rank} " if rank is not None else ""

        return f"""
## {rank_text}{job.get("title")} — {job.get("company")}

**Score:** {job.get("score")}/100  
**Recommendation:** {job.get("recommendation")}  
**Location:** {job.get("location")}  
**Listed at:** {job.get("listed_at")}  
**Link:** {job.get("url")}

**Fit summary:**  
{job.get("fit_summary")}

**Why it matches:**  
{list_md(job.get("match_reasons", []))}

**Concerns:**  
{list_md(job.get("concerns", []))}

**Matched skills:**  
{list_md(job.get("matched_skills", []))}

**Missing / weak skills:**  
{list_md(job.get("missing_or_weak_skills", []))}

---
""".strip()

    top_5_text = "\n\n".join(
        job_block(job, rank=index) for index, job in enumerate(top_5, start=1)
    )

    rest_text = "\n\n".join(job_block(job) for job in rest)

    if not rest_text:
        rest_text = "No additional jobs found."

    report = f"""
# {report_title}

Found and scored **{len(scored_jobs)}** fresh jobs.

# Top 5 Best Matches

{top_5_text}

# Remaining Jobs

{rest_text}
""".strip()

    path = save_report(report, report_name=report_title)
    report_path = Path(path)
    snapshot_path = REPORTS_DIR / f"{report_path.stem}.json"
    snapshot = {
        "status": "complete",
        "report_path": str(report_path),
        "report_name": report_path.name,
        "report_title": report_title,
        "target_industry": display_target_industry,
        "report": report,
        "top_jobs": top_5,
        "remaining_jobs": rest,
        "job_count": len(scored_jobs),
    }
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    return {
        "report": report,
        "report_path": path,
        "report_name": report_path.name,
        "report_title": report_title,
        "top_jobs": top_5,
        "remaining_jobs": rest,
        "target_industry": display_target_industry,
        "job_count": len(scored_jobs),
    }


@tool
def send_email_report(subject: str, report: str) -> dict:
    """Send the daily job report by email."""
    _tool_log("send_email_report")
    return send_email(subject=subject, body=report)


@tool
def save_reported_jobs(scored_jobs: List[Dict[str, Any]]) -> dict:
    """Save reported job IDs so future reports can avoid repeats."""
    _tool_log("save_reported_jobs")
    job_ids = []

    for job in scored_jobs:
        job_id = job.get("job_id") or job.get("url")

        if job_id:
            job_ids.append(job_id)

    save_seen_job_ids(job_ids)

    return {"saved_count": len(job_ids)}


@tool
def mark_report_complete_today() -> dict:
    """Mark today's daily job report as sent."""
    _tool_log("mark_report_complete_today")
    mark_sent_today()

    return {"marked_complete": True, "date": datetime.now().strftime("%Y-%m-%d")}


def _run_search_pipeline_core(
    target_industry: str = "software engineer",
    location: str = "United States",
    pages: int = 1,
    should_email: bool = False,
    to_email: str = "",
) -> dict:
    run_id = _current_chat_run_id()

    try:
        if is_search_run_canceled(run_id):
            raise RuntimeError("Search was canceled by user.")

        set_search_run_progress(
            run_id,
            status="running",
            progress=15,
            step="Fetching jobs",
            result={
                "phase": "fetching",
                "current_job_title": "",
                "scraped_count": 0,
                "found_so_far": 0,
            },
        )
        try:
            profile = load_profile_from_files()
        except FileNotFoundError as error:
            set_search_run_progress(
                run_id,
                status="failed",
                progress=100,
                step="Missing resume",
                error=str(error),
                result={
                    "phase": "failed",
                    "status": "missing_resume",
                    "message": str(error),
                },
            )
            return {
                "status": "missing_resume",
                "message": str(error),
                "error": str(error),
            }

        resume_text = str(profile.get("resume_text", "") or "")
        preferences_text = str(profile.get("preferences_text", "") or "")
        if not resume_text.strip():
            message = "No resume found. Add either profile/resume.pdf or profile/resume.txt."
            set_search_run_progress(
                run_id,
                status="failed",
                progress=100,
                step="Missing resume",
                error=message,
                result={
                    "phase": "failed",
                    "status": "missing_resume",
                    "message": message,
                },
            )
            return {
                "status": "missing_resume",
                "message": message,
                "error": message,
            }
        memory_text = memory_as_text()

        search_term = str(target_industry or "").strip() or "software engineer"
        jobs = scrape_jobs(
            keywords=search_term,
            location=location,
            pages=int(max(1, min(10, pages))),
            is_canceled=lambda: is_search_run_canceled(run_id),
            on_job_found=lambda **payload: set_search_run_progress(
                run_id,
                status="running",
                progress=20,
                step="Fetching jobs",
                result={
                    "phase": "fetching",
                    "current_job_title": str(payload.get("job", {}).get("title", "")),
                    "current_job_company": str(payload.get("job", {}).get("company", "")),
                    "scraped_count": int(payload.get("job_index", 0) or 0),
                    "page_index": int(payload.get("page_index", 0) or 0),
                    "page_count": int(payload.get("page_count", 0) or 0),
                    "job_index": int(payload.get("job_index", 0) or 0),
                    "page_job_count": int(payload.get("page_job_count", 0) or 0),
                },
            ),
        )
        if is_search_run_canceled(run_id):
            raise RuntimeError("Search was canceled by user.")

        seen = load_seen_job_ids()
        fresh_jobs = [
            job for job in jobs if (job.get("job_id") or job.get("url")) not in seen
        ]

        found_count = len(jobs)

        if not fresh_jobs:
            set_search_run_progress(
                run_id,
                status="complete",
                progress=100,
                step="Completed",
                result={
                    "phase": "complete",
                    "scraped_count": found_count,
                    "fresh_count": 0,
                    "scored_count": 0,
                    "report_path": "",
                    "report_name": "",
                    "target_industry": search_term,
                },
            )
            return {
                "status": "no_new_jobs",
                "target_industry": search_term,
                "keywords": search_term,
                "location": location,
                "pages": int(max(1, min(10, pages))),
                "scraped_count": len(jobs),
                "fresh_count": 0,
                "scored_count": 0,
                "report_path": "",
                "report_name": "",
                "report": "",
                "top_jobs": [],
                "remaining_jobs": [],
                "email_result": None,
                "assistant_message": "No new jobs were found. All matching jobs on the selected pages have already been seen.",
            }

        set_search_run_progress(
            run_id, status="running", progress=70, step="Scoring jobs"
        )
        scored_jobs = score_jobs(
            jobs=fresh_jobs,
            resume_text=resume_text,
            preferences_text=preferences_text + "\n\nSaved memory:\n" + memory_text,
            is_canceled=lambda: is_search_run_canceled(run_id),
            on_progress=lambda **payload: set_search_run_progress(
                run_id,
                status="running",
                progress=70 + int((payload.get("index", 0) / max(1, int(payload.get("total", 1)))) * 18),
                step="Scoring jobs",
                result={
                    "phase": "scoring",
                    "scoring_index": int(payload.get("index", 0) or 0),
                    "scoring_total": int(payload.get("total", 0) or 0),
                    "current_job_title": str(payload.get("job", {}).get("title", "")),
                    "current_job_company": str(payload.get("job", {}).get("company", "")),
                    "scraped_count": found_count,
                },
            ),
        )
        if is_search_run_canceled(run_id):
            raise RuntimeError("Search was canceled by user.")

        set_search_run_progress(
            run_id, status="running", progress=90, step="Building report"
        )
        report_payload = build_daily_report.func(  # type: ignore[attr-defined]
            scored_jobs={"scored_jobs": scored_jobs, "target_industry": search_term}
        )

        job_ids = []
        for job in scored_jobs:
            job_id = job.get("job_id") or job.get("url")
            if job_id:
                job_ids.append(job_id)
        save_seen_job_ids(job_ids)

        email_result = None
        if should_email:
            email_result = send_email(
                subject=f"{search_term.title()} Job Report - {datetime.now().strftime('%Y-%m-%d')}",
                body=str(report_payload.get("report", "")),
                to_email=str(to_email).strip(),
            )

        set_search_run_progress(
            run_id, status="complete", progress=100, step="Completed"
        )
        return {
            "status": "complete",
            "target_industry": search_term,
            "keywords": search_term,
            "location": location,
            "pages": int(max(1, min(10, pages))),
            "scraped_count": len(jobs),
            "fresh_count": len(fresh_jobs),
            "scored_count": len(scored_jobs),
            "report_path": report_payload.get("report_path"),
            "report_name": report_payload.get("report_name"),
            "report": report_payload.get("report"),
            "top_jobs": report_payload.get("top_jobs", []),
            "remaining_jobs": report_payload.get("remaining_jobs", []),
            "email_result": email_result,
        }
    finally:
        clear_search_run_cancel(run_id)


@tool
def run_search_pipeline(
    target_industry: str = "software engineer",
    location: str = "United States",
    pages: int = 1,
    should_email: bool = False,
    to_email: str = "",
) -> dict:
    """
    Run the full search pipeline in one tool call.
    The agent should use this for every new search request.
    """
    _tool_log("run_search_pipeline")
    return _run_search_pipeline_core(
        target_industry=target_industry,
        location=location,
        pages=pages,
        should_email=should_email,
        to_email=to_email,
    )


@tool
def get_most_recent_job_report() -> dict:
    """
    Load the most recent saved Markdown job report from the reports folder.
    Use this when the user asks to see, resend, or email the most recent existing report.
    This tool does not scrape jobs and does not create a new report.
    """

    _tool_log("get_most_recent_job_report")
    return load_latest_report()


@tool
def email_most_recent_job_report() -> dict:
    """
    Email the most recent saved job report.
    Use this when the user asks to email the latest report without performing a new search.
    This tool must not scrape jobs or create a fresh report.
    """

    _tool_log("email_most_recent_job_report")
    result = load_latest_report()

    if not result["found"]:
        return {
            "status": "failed",
            "message": "No saved job report was found in the reports folder.",
        }

    subject = "Most Recent SWE Job Report"

    email_result = send_email(subject=subject, body=result["report"])

    return {
        "status": "sent_existing_report",
        "report_path": result["report_path"],
        "email_result": email_result,
    }


@tool
def display_latest_report_in_chat() -> dict:
    """
    Load the latest report payload for chat display.
    Use this when the user asks to show/display/open the latest report in chat.
    This does not run a new search.
    """
    _tool_log("display_latest_report_in_chat")
    return get_latest_report()


@tool
def update_search_schedule_from_chat(
    enabled: bool | None = None,
    time: str | None = None,
    days: dict[str, bool] | None = None,
    keywords: str | None = None,
    location: str | None = None,
    pages: int | None = None,
    email_to: str | None = None,
) -> dict:
    """
    Update scheduler settings from chat instructions.
    Only provided fields are changed; unspecified fields are preserved.
    """
    _tool_log("update_search_schedule_from_chat")
    current = get_search_schedule()
    payload = dict(current)
    if enabled is not None:
        payload["enabled"] = bool(enabled)
    if time is not None:
        payload["time"] = str(time)
    if days is not None:
        payload["days"] = dict(days)
    if keywords is not None:
        payload["keywords"] = str(keywords)
    if location is not None:
        payload["location"] = str(location)
    if pages is not None:
        payload["pages"] = int(pages)
    if email_to is not None:
        payload["email_to"] = str(email_to)
    updated = save_search_schedule(payload)
    return {"status": "updated", "schedule": updated}


@tool
def update_preferences_from_chat(
    preferences_text: str,
    target_industry: str = "",
) -> dict:
    """
    Overwrite preferences text based on user chat request.
    If target_industry is provided, it is inserted as:
    Target Industry: <value>
    at the top of preferences unless already present.
    """
    _tool_log("update_preferences_from_chat")
    text = str(preferences_text or "").strip()
    if not text:
        return {"status": "failed", "message": "preferences_text cannot be empty"}

    industry = str(target_industry or "").strip()
    if industry:
        first_line = f"Target Industry: {industry}"
        if "target industry:" not in text.lower():
            text = f"{first_line}\n{text}"

    result = save_preferences(text)
    saved = get_preferences()
    return {
        "status": "updated",
        "result": result,
        "preferences": saved.get("preferences", ""),
    }


@tool
def display_report_in_chat(
    report_name: str = "",
    order: int = 0,
) -> dict:
    """
    Display a specific saved report in chat by name or by order.
    - If report_name is provided, tries exact then partial case-insensitive match.
    - Else if order > 0, opens that report by recency order (1 = most recent).
    - Else falls back to latest report.
    """
    _tool_log("display_report_in_chat")
    reports_payload = list_reports()
    reports = list(reports_payload.get("reports", []))
    if not reports:
        return {"found": False, "message": "No saved reports found."}

    selected_path = ""
    name_query = str(report_name or "").strip().lower()
    if name_query:
        exact = next(
            (
                r
                for r in reports
                if str(r.get("name", "")).strip().lower() == name_query
            ),
            None,
        )
        if exact:
            selected_path = str(exact.get("report_path", ""))
        else:
            partial = next(
                (
                    r
                    for r in reports
                    if name_query in str(r.get("name", "")).strip().lower()
                ),
                None,
            )
            if partial:
                selected_path = str(partial.get("report_path", ""))
    elif int(order or 0) > 0:
        idx = int(order) - 1
        if 0 <= idx < len(reports):
            selected_path = str(reports[idx].get("report_path", ""))

    if not selected_path:
        latest = reports[0]
        selected_path = str(latest.get("report_path", ""))

    try:
        return get_report_by_path(selected_path)
    except Exception as error:
        return {"found": False, "message": f"Failed to load report: {error}"}


@tool
def read_profile_preferences() -> dict:
    """
    Read the current target industry and preferences from saved profile preferences.
    Use this when the user asks what their current preferences/industry are.
    """
    _tool_log("read_profile_preferences")
    payload = get_preferences()
    text = str(payload.get("preferences", "") or "")
    target_industry = ""

    for line in text.splitlines():
        match = re.match(
            r"^\s*target\s*industry\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE
        )
        if match:
            target_industry = match.group(1).strip()
            break

    return {
        "found": bool(payload.get("found")),
        "target_industry": target_industry,
        "preferences": text,
    }


@tool
def set_chat_search_running_state(
    step: str = "Fetching jobs",
    progress: int = 15,
) -> dict:
    """
    Set frontend-visible chat search state to running.
    Call this immediately before running search tools from chat flows.
    """
    _tool_log("set_chat_search_running_state")
    return set_search_run_progress(
        _current_chat_run_id(),
        status="running",
        progress=int(progress),
        step=str(step or "Fetching jobs"),
    )


@tool
def run_search_report_and_email(
    keywords: str = "software engineer",
    location: str = "United States",
    pages: int = 1,
    to_email: str = "",
) -> dict:
    """
    Deterministic end-to-end pipeline for chat requests.
    This legacy helper is kept for internal use and email flows.
    """
    _tool_log("run_search_report_and_email")
    return _run_search_pipeline_core(
        target_industry=keywords,
        location=location,
        pages=pages,
        to_email=to_email,
    )
