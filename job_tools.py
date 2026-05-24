from datetime import datetime
from typing import List, Dict, Any

from langchain.tools import tool

from linkedin_scraper import scrape_jobs
from job_scorer import score_jobs
from storage import (
    load_seen_job_ids,
    save_seen_job_ids,
    already_sent_today,
    mark_sent_today,
    save_report,
)
from emailer import send_email


@tool
def check_report_sent_today() -> dict:
    """Check whether today's job report has already been sent."""
    return {
        "already_sent_today": already_sent_today()
    }


@tool
def load_candidate_profile() -> dict:
    """Load the candidate's resume and job preferences from local text files."""
    with open("resume.txt", "r", encoding="utf-8") as file:
        resume_text = file.read().strip()

    with open("preferences.txt", "r", encoding="utf-8") as file:
        preferences_text = file.read().strip()

    return {
        "resume_text": resume_text,
        "preferences_text": preferences_text,
    }


@tool
def scrape_linkedin_jobs_tool(
    keywords: str = "software engineer",
    location: str = "United States",
    pages: int = 2
) -> dict:
    """
    Scrape public LinkedIn guest job results for a keyword and location.
    Returns job cards with descriptions.
    """

    jobs = scrape_jobs(
        keywords=keywords,
        location=location,
        pages=pages
    )

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
    preferences_text: str,
    memory_text: str = ""
) -> dict:
    """Score a list of jobs from 1 to 100 against the candidate's resume, preferences, and saved memory."""
    scored = score_jobs(
        jobs=jobs,
        resume_text=resume_text,
        preferences_text=preferences_text + "\n\nSaved memory:\n" + memory_text,
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

    today = datetime.now().strftime("%Y-%m-%d")

    scored_jobs = sorted(
        scored_jobs,
        key=lambda item: item.get("score", 0),
        reverse=True
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
        job_block(job, rank=index)
        for index, job in enumerate(top_5, start=1)
    )

    rest_text = "\n\n".join(job_block(job) for job in rest)

    if not rest_text:
        rest_text = "No additional jobs found."

    report = f"""
# Daily Software Engineering Job Report — {today}

Found and scored **{len(scored_jobs)}** fresh jobs.

# Top 5 Best Matches

{top_5_text}

# Remaining Jobs

{rest_text}
""".strip()

    path = save_report(report)

    return {
        "report": report,
        "report_path": path,
        "job_count": len(scored_jobs),
    }


@tool
def send_email_report(subject: str, report: str) -> dict:
    """Send the daily job report by email."""
    return send_email(subject=subject, body=report)


@tool
def save_reported_jobs(scored_jobs: List[Dict[str, Any]]) -> dict:
    """Save reported job IDs so future reports can avoid repeats."""
    job_ids = []

    for job in scored_jobs:
        job_id = job.get("job_id") or job.get("url")

        if job_id:
            job_ids.append(job_id)

    save_seen_job_ids(job_ids)

    return {
        "saved_count": len(job_ids)
    }


@tool
def mark_report_complete_today() -> dict:
    """Mark today's daily job report as sent."""
    mark_sent_today()

    return {
        "marked_complete": True,
        "date": datetime.now().strftime("%Y-%m-%d")
    }