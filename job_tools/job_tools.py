from datetime import datetime
from typing import List, Dict, Any
import re
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain.tools import tool

from job_tools.resume_loader import (
    load_candidate_profile as load_profile_from_files,
    refresh_resume_text_from_pdf,
)
from job_tools.linkedin_scraper import scrape_jobs
from job_tools.job_scorer import score_jobs
from job_tools.search_pipeline import collect_filtered_search_jobs
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
from job_tools.memory_store import add_search_history
from job_tools.memory_store import get_last_target_industry, set_last_target_industry
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
    get_current_time_zone,
    get_current_resume_display_name,
)


def _current_chat_run_id() -> str:
    run_id = str(get_current_run_id() or "").strip()
    return run_id or CHAT_AGENT_RUN_ID


def _tool_log(name: str) -> None:
    print(f"TOOL: {name}")


def _now_in_current_timezone() -> datetime:
    timezone_name = str(get_current_time_zone() or "UTC").strip() or "UTC"
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        return datetime.now()


def _normalize_location(location: str) -> str:
    text = str(location or "").strip()
    if not text:
        return "United States"

    lower = text.lower()
    if "remote" in lower and "united states" not in lower and "usa" not in lower and "us" not in lower:
        return "Remote, United States"

    return text


def _resolve_target_industry(target_industry: str) -> str:
    text = str(target_industry or "").strip()
    if text:
        return text
    return get_last_target_industry()


def _normalize_job_level(job_level: str) -> str:
    text = str(job_level or "").strip()
    if not text:
        return ""

    lower = text.lower()
    if lower in {"jr", "entry", "entry level", "junior"}:
        return "junior"
    if lower in {"mid", "mid level", "mid-level", "intermediate"}:
        return "intermediate"
    if lower in {"sr", "senior", "senior level", "lead", "staff", "principal"}:
        return "senior"
    return text


def _build_search_keywords(target_industry: str, company: str = "", job_level: str = "") -> str:
    parts = [str(target_industry or "").strip()]
    normalized_level = _normalize_job_level(job_level)
    if normalized_level:
        parts.append(normalized_level)
    company_text = str(company or "").strip()
    if company_text:
        parts.append(company_text)
    return " ".join(part for part in parts if part)


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
    now = _now_in_current_timezone()
    date_text = now.strftime("%B %d, %Y").replace(" 0", " ")
    time_text = f"{now.hour}:{now.strftime('%M')}"
    return f"{role_text} · {date_text}, {time_text}"


def _format_recommendation_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "apply": "Apply",
        "apply_today": "Apply",
        "review": "Review",
        "maybe": "Maybe",
        "ignore": "Ignore",
    }.get(normalized, str(value or "").strip().title())


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
    keywords: str = "", location: str = "United States", pages: int = 1
) -> dict:
    """
    Scrape public LinkedIn guest job results for a keyword and location.
    Returns job cards with descriptions.
    """

    _tool_log("scrape_linkedin_jobs_tool")
    search_term = str(keywords or "").strip()
    if not search_term:
        raise ValueError("keywords cannot be empty.")

    jobs = scrape_jobs(keywords=search_term, location=_normalize_location(location), pages=pages)

    return {
        "keywords": search_term,
        "location": _normalize_location(location),
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

    target_industry = ""

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

    display_target_industry = target_industry.strip()
    report_role = _extract_report_role(display_target_industry, scored_jobs) if display_target_industry else "Job Search"
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
**Recommendation:** {_format_recommendation_label(job.get("recommendation"))}  
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

    return {"marked_complete": True, "date": _now_in_current_timezone().strftime("%Y-%m-%d")}


def _run_search_pipeline_core(
    target_industry: str = "",
    company: str = "",
    job_level: str = "",
    location: str = "United States",
    pages: int = 1,
    should_email: bool = False,
    to_email: str = "",
) -> dict:
    run_id = _current_chat_run_id()

    try:
        if is_search_run_canceled(run_id):
            raise RuntimeError("Search was canceled by user.")

        search_term = _resolve_target_industry(target_industry)
        if not search_term:
            message = "Specify a target industry before searching."
            if run_id:
                set_search_run_progress(
                    run_id,
                    status="failed",
                    progress=100,
                    step="Missing target industry",
                    error=message,
                    result={
                        "phase": "failed",
                        "status": "missing_target_industry",
                        "message": message,
                    },
                )
            return {
                "status": "missing_target_industry",
                "message": message,
                "error": message,
            }

        search_location = _normalize_location(location)
        search_company = str(company or "").strip()
        search_job_level = _normalize_job_level(job_level)
        search_keywords = _build_search_keywords(search_term, search_company, search_job_level)

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

        set_search_run_progress(
            run_id,
            status="running",
            progress=20,
            step="Fetching jobs",
            result={
                "phase": "fetching",
                "current_job_title": "",
                "current_job_company": "",
                "scraped_count": 0,
                "found_so_far": 0,
            },
        )

        search_result = collect_filtered_search_jobs(
            target_industry=search_term,
            company=search_company,
            job_level=search_job_level,
            location=search_location,
            requested_pages=pages,
            minimum_jobs=3,
            max_pages=10,
            is_canceled=lambda: is_search_run_canceled(run_id),
            on_job_progress=lambda payload: set_search_run_progress(
                run_id,
                status="running",
                progress=min(40, 20 + int((payload.get("job_index", 1) / max(1, int(payload.get("page_job_count", 1)))) * 15)),
                step="Fetching job details",
                result={
                    "phase": "fetching",
                    "current_job_title": str(payload.get("job", {}).get("title", "")),
                    "current_job_company": str(payload.get("job", {}).get("company", "")),
                    "scraped_count": int(payload.get("job_index", 0) or 0),
                    "page_index": int(payload.get("page_index", 0) or 0),
                    "page_job_count": int(payload.get("page_job_count", 0) or 0),
                    "search_keywords": str(payload.get("search_keywords", "") or ""),
                    "location": str(payload.get("location", "") or ""),
                },
            ),
            on_filter_progress=lambda payload: set_search_run_progress(
                run_id,
                status="running",
                progress=40 + int(
                    (payload.get("job_index", 0) / max(1, int(payload.get("job_total", 1))))
                    * 25
                ),
                step="Filtering",
                result={
                    "phase": "filtering",
                    "current_job_title": str(payload.get("job", {}).get("title", "")),
                    "current_job_company": str(payload.get("job", {}).get("company", "")),
                    "filtering_index": int(payload.get("job_index", 0) or 0),
                    "filtering_total": int(payload.get("job_total", 0) or 0),
                    "kept_count": int(payload.get("kept_count", 0) or 0),
                    "rejected_count": int(payload.get("rejected_count", 0) or 0),
                },
            ),
            on_page_progress=lambda payload: set_search_run_progress(
                run_id,
                status="running",
                progress=min(65, 20 + int((payload.get("pages_checked", 1) / max(1, max(3, int(pages)))) * 35)),
                step="Filtering",
                result={
                    "phase": "filtering",
                    "current_job_title": str(payload.get("current_job_title", "") or ""),
                    "current_job_company": str(payload.get("current_job_company", "") or ""),
                    "scraped_count": int(payload.get("scraped_count", 0) or 0),
                    "pages_checked": int(payload.get("pages_checked", 0) or 0),
                    "page_index": int(payload.get("page_index", 0) or 0),
                    "unique_count": int(payload.get("unique_count", 0) or 0),
                    "kept_count": int(payload.get("kept_count", 0) or 0),
                    "duplicate_count": int(payload.get("duplicate_count", 0) or 0),
                    "rejected_count": int(payload.get("rejected_count", 0) or 0),
                    "seen_count": int(payload.get("seen_count", 0) or 0),
                    "search_keywords": str(payload.get("search_keywords", "") or ""),
                    "location": str(payload.get("location", "") or ""),
                },
            ),
        )
        if is_search_run_canceled(run_id):
            raise RuntimeError("Search was canceled by user.")

        jobs = search_result.jobs
        found_count = search_result.scraped_count
        search_keywords = search_result.search_keywords
        search_location = search_result.location
        search_company = search_result.company
        search_job_level = search_result.job_level

        if not jobs:
            no_jobs_message = (
                f"No matching jobs were found after checking {search_result.jobs_checked} jobs."
                if search_result.no_match_timeout_triggered
                else "No new jobs were found after filtering duplicates and mismatches."
            )
            set_search_run_progress(
                run_id,
                status="complete",
                progress=100,
                step="Completed",
                result={
                    "phase": "complete",
                    "scraped_count": found_count,
                    "jobs_checked": search_result.jobs_checked,
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
                "keywords": search_keywords,
                "company": search_company,
                "job_level": search_job_level,
                "location": search_location,
                "pages": int(max(1, min(10, pages))),
                "scraped_count": found_count,
                "fresh_count": 0,
                "scored_count": 0,
                "report_path": "",
                "report_name": "",
                "report": "",
                "top_jobs": [],
                "remaining_jobs": [],
                "email_result": None,
                "assistant_message": no_jobs_message,
            }

        fresh_count = len(jobs)
        set_search_run_progress(
            run_id,
            status="running",
            progress=70,
            step="Scoring jobs",
            result={
                "phase": "scoring",
                "fresh_count": fresh_count,
                "scraped_count": found_count,
            },
        )
        scored_jobs = score_jobs(
            jobs=jobs,
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
                    "fresh_count": fresh_count,
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
            scored_jobs={
                "scored_jobs": scored_jobs,
                "target_industry": search_term,
                "keywords": search_keywords,
            }
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
                subject=f"{search_term.title()} Job Report - {_now_in_current_timezone().strftime('%Y-%m-%d')}",
                body=str(report_payload.get("report", "")),
                to_email=str(to_email).strip(),
            )

        set_search_run_progress(
            run_id, status="complete", progress=100, step="Completed"
        )
        return {
            "status": "complete",
            "target_industry": search_term,
            "keywords": search_keywords,
            "company": search_company,
            "job_level": search_job_level,
            "location": search_location,
            "pages": int(max(1, min(10, pages))),
            "scraped_count": found_count,
            "fresh_count": fresh_count,
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
    target_industry: str = "",
    company: str = "",
    job_level: str = "",
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
    active_resume_display_name = get_current_resume_display_name()
    if not active_resume_display_name:
        run_id = _current_chat_run_id()
        message = "Select a resume in the UI before searching."
        if run_id:
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
    resolved_target_industry = _resolve_target_industry(target_industry)
    if not resolved_target_industry:
        run_id = _current_chat_run_id()
        message = "Specify a target industry before searching."
        if run_id:
            set_search_run_progress(
                run_id,
                status="failed",
                progress=100,
                step="Missing target industry",
                error=message,
                result={
                    "phase": "failed",
                    "status": "missing_target_industry",
                    "message": message,
                },
            )
        return {
            "status": "missing_target_industry",
            "message": message,
            "error": message,
        }
    run_id = _current_chat_run_id()
    status = "failed"
    result: dict = {}
    cancelled = False
    try:
        result = _run_search_pipeline_core(
            target_industry=resolved_target_industry,
            company=company,
            job_level=job_level,
            location=location,
            pages=pages,
            should_email=should_email,
            to_email=to_email,
        )
        status = str(result.get("status", "complete") or "complete")
        return result
    except RuntimeError as error:
        cancelled = "Search was canceled by user." in str(error)
        status = "canceled" if cancelled else "failed"
        raise
    finally:
        if run_id:
            try:
                add_search_history(
                    run_id=run_id,
                    target_industry=resolved_target_industry,
                    company=str(company or "").strip(),
                    job_level=_normalize_job_level(job_level),
                    location=_normalize_location(location),
                    pages=pages,
                    status=status,
                    scraped_count=int(result.get("scraped_count", 0) or 0),
                    fresh_count=int(result.get("fresh_count", 0) or 0),
                    scored_count=int(result.get("scored_count", 0) or 0),
                    report_path=str(result.get("report_path", "") or ""),
                    report_name=str(result.get("report_name", "") or ""),
                    assistant_message=str(result.get("assistant_message", "") or ""),
                    cancelled=cancelled,
                )
            except Exception:
                pass
        if status in {"complete", "no_new_jobs"} and resolved_target_industry:
            set_last_target_industry(resolved_target_industry)


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
    keywords: str = "",
    company: str = "",
    job_level: str = "",
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
        company=company,
        job_level=job_level,
        location=location,
        pages=pages,
        to_email=to_email,
    )
