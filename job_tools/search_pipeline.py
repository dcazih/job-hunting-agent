from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from job_tools.linkedin_scraper import scrape_jobs
from job_tools.storage import load_seen_job_ids

load_dotenv()


class JobRelevanceDecision(BaseModel):
    keep: bool
    reason: str = ""


@dataclass
class SearchFilterResult:
    jobs: list[dict[str, Any]]
    search_keywords: str
    location: str
    target_industry: str
    company: str
    job_level: str
    pages_checked: int
    jobs_checked: int
    scraped_count: int
    duplicate_count: int
    rejected_count: int
    seen_count: int
    no_match_timeout_triggered: bool


def normalize_location(location: str) -> str:
    text = str(location or "").strip()
    if not text:
        return "United States"

    lower = text.lower()
    if "remote" in lower and "united states" not in lower and "usa" not in lower and "us" not in lower:
        return "Remote, United States"

    return text


def normalize_job_level(job_level: str) -> str:
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


def build_search_keywords(target_industry: str, company: str = "", job_level: str = "") -> str:
    parts = [str(target_industry or "").strip()]
    normalized_level = normalize_job_level(job_level)
    if normalized_level:
        parts.append(normalized_level)
    company_text = str(company or "").strip()
    if company_text:
        parts.append(company_text)
    return " ".join(part for part in parts if part)


def _dedupe_key(job: dict[str, Any]) -> str:
    job_id = str(job.get("job_id") or "").strip()
    if job_id:
        return f"id:{job_id}"

    url = str(job.get("url") or "").strip()
    if url:
        return f"url:{url}"

    title = " ".join(str(job.get("title") or "").lower().split())
    company = " ".join(str(job.get("company") or "").lower().split())
    location = " ".join(str(job.get("location") or "").lower().split())
    return f"fallback:{title}|{company}|{location}"


def dedupe_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_jobs: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for job in jobs:
        key = _dedupe_key(job)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_jobs.append(job)

    return unique_jobs


def _get_relevance_model():
    model_name = os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini")
    return ChatOpenAI(
        model=model_name.replace("openai:", ""),
        temperature=0,
        timeout=float(os.getenv("JOB_FILTER_LLM_TIMEOUT_SECONDS", "12")),
        max_retries=0,
    ).with_structured_output(JobRelevanceDecision)


def _job_text(job: dict[str, Any]) -> str:
    description = str(job.get("description", "") or "")
    if len(description) > 5000:
        description = description[:5000] + "\n\n[TRUNCATED]"
    return description


def _should_keep_job(
    job: dict[str, Any],
    *,
    target_industry: str,
    company: str,
    job_level: str,
    location: str,
) -> JobRelevanceDecision:
    model = _get_relevance_model()
    print(f"LLM filtering job: {job.get('title')} at {job.get('company')}")
    prompt = f"""
You are a strict job search filter.

Keep the job only if it clearly matches the user's request. Be conservative.

User request:
- target industry: {target_industry or "unspecified"}
- company: {company or "unspecified"}
- job level: {job_level or "unspecified"}
- location: {location or "United States"}

Rules:
- If company is specified, keep only jobs at that company or clearly for that employer.
- If job level is specified, keep only jobs that match that seniority.
- If the location is Remote or United States, keep remote jobs in the USA and jobs that explicitly fit that location.
- If the job is unrelated, clearly senior when junior was requested, or otherwise does not fit, discard it.
- If unsure, discard it.

Job:
Title: {job.get("title")}
Company: {job.get("company")}
Location: {job.get("location")}
Listed at: {job.get("listed_at")}
URL: {job.get("url")}

Description:
{_job_text(job)}
"""
    decision = model.invoke(prompt)
    verdict = "keep" if decision.keep else "discard"
    print(
        f"LLM filter result: {verdict} for {job.get('title')} at {job.get('company')}"
    )
    return decision


def filter_jobs_against_request(
    jobs: list[dict[str, Any]],
    *,
    target_industry: str,
    company: str = "",
    job_level: str = "",
    location: str = "United States",
    is_canceled: Callable[[], bool] | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_filter_progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    kept_jobs: list[dict[str, Any]] = []
    rejected_count = 0
    normalized_location = normalize_location(location)
    normalized_company = str(company or "").strip()
    normalized_level = normalize_job_level(job_level)

    total_jobs = len(jobs)
    for job_index, job in enumerate(jobs, start=1):
        if callable(is_canceled) and is_canceled():
            raise RuntimeError("Search was canceled by user.")
        if callable(should_stop) and should_stop():
            break
        if callable(on_filter_progress):
            on_filter_progress(
                {
                    "job": job,
                    "job_index": job_index,
                    "job_total": total_jobs,
                    "kept_count": len(kept_jobs),
                    "rejected_count": rejected_count,
                }
            )
        print(f"Applying LLM job filter: {job.get('title')} at {job.get('company')}")
        try:
            decision = _should_keep_job(
                job,
                target_industry=target_industry,
                company=normalized_company,
                job_level=normalized_level,
                location=normalized_location,
            )
        except Exception as error:
            print(
                f"LLM filter failed for {job.get('title')} at {job.get('company')}: {error}"
            )
            rejected_count += 1
            continue

        if decision.keep:
            kept_jobs.append(job)
        else:
            rejected_count += 1

    return kept_jobs, rejected_count


def collect_filtered_search_jobs(
    *,
    target_industry: str,
    company: str = "",
    job_level: str = "",
    location: str = "United States",
    requested_pages: int = 1,
    minimum_jobs: int = 3,
    max_pages: int = 10,
    no_match_job_limit: int = 20,
    max_runtime_seconds: float | None = None,
    is_canceled: Callable[[], bool] | None = None,
    on_job_progress: Callable[[dict[str, Any]], None] | None = None,
    on_filter_progress: Callable[[dict[str, Any]], None] | None = None,
    on_page_progress: Callable[[dict[str, Any]], None] | None = None,
) -> SearchFilterResult:
    normalized_location = normalize_location(location)
    normalized_company = str(company or "").strip()
    normalized_level = normalize_job_level(job_level)
    search_keywords = build_search_keywords(target_industry, normalized_company, normalized_level)
    seen_ids = set(load_seen_job_ids())
    collected_jobs: list[dict[str, Any]] = []
    pages_checked = 0
    jobs_checked = 0
    duplicate_count = 0
    rejected_count = 0
    seen_count = 0
    consecutive_empty_pages = 0
    requested_pages = max(1, int(requested_pages or 1))
    max_pages = max(requested_pages, minimum_jobs, int(max_pages or 1))
    no_match_job_limit = max(1, int(no_match_job_limit or 1))
    runtime_limit = (
        float(max_runtime_seconds)
        if max_runtime_seconds is not None
        else float(os.getenv("SEARCH_PIPELINE_MAX_RUNTIME_SECONDS", "150" if os.getenv("VERCEL") else "0"))
    )
    deadline = time.monotonic() + runtime_limit if runtime_limit > 0 else None
    runtime_limit_triggered = False
    processed_keys: set[str] = set()
    filtered_jobs: list[dict[str, Any]] = []

    def should_stop() -> bool:
        nonlocal runtime_limit_triggered
        if deadline is not None and time.monotonic() >= deadline:
            runtime_limit_triggered = True
            return True
        return False

    for page_index in range(max_pages):
        if callable(is_canceled) and is_canceled():
            raise RuntimeError("Search was canceled by user.")
        if should_stop():
            break

        current_job_snapshot: dict[str, Any] = {}
        page_jobs = scrape_jobs(
            keywords=search_keywords,
            location=normalized_location,
            pages=1,
            start_page=page_index,
            max_jobs=max(0, no_match_job_limit - jobs_checked),
            is_canceled=is_canceled,
            on_job_found=lambda **payload: on_job_progress(
                {
                    "page_index": int(payload.get("page_index", 0) or 0),
                    "page_count": int(payload.get("page_count", 0) or 0),
                    "job_index": int(payload.get("job_index", 0) or 0),
                    "page_job_count": int(payload.get("page_job_count", 0) or 0),
                    "job": dict(payload.get("job", {}) or {}),
                    "search_keywords": search_keywords,
                    "location": normalized_location,
                }
            )
            if callable(on_job_progress)
            else None,
        )
        if callable(on_job_progress):
            for job in page_jobs[-1:]:
                current_job_snapshot = {"current_job_title": str(job.get("title", "") or ""), "current_job_company": str(job.get("company", "") or "")}
        pages_checked += 1
        collected_jobs.extend(page_jobs)

        if page_jobs:
            consecutive_empty_pages = 0
        else:
            consecutive_empty_pages += 1

        deduped_jobs = dedupe_jobs(collected_jobs)
        duplicate_count = len(collected_jobs) - len(deduped_jobs)
        jobs_checked = len(deduped_jobs)

        new_jobs = []
        for job in deduped_jobs:
            key = _dedupe_key(job)
            if key in processed_keys:
                continue
            processed_keys.add(key)
            new_jobs.append(job)

        newly_filtered_jobs, page_rejected_count = filter_jobs_against_request(
            new_jobs,
            target_industry=target_industry,
            company=normalized_company,
            job_level=normalized_level,
            location=normalized_location,
            is_canceled=is_canceled,
            should_stop=should_stop,
            on_filter_progress=on_filter_progress,
        )
        filtered_jobs.extend(newly_filtered_jobs)
        rejected_count += page_rejected_count

        fresh_jobs = []
        seen_count = 0
        for job in filtered_jobs:
            job_key = str(job.get("job_id") or job.get("url") or "").strip()
            if job_key and job_key in seen_ids:
                seen_count += 1
                continue
            fresh_jobs.append(job)

        if callable(on_page_progress):
            on_page_progress(
                {
                    "page_index": page_index + 1,
                    "pages_checked": pages_checked,
                    "scraped_count": len(collected_jobs),
                    "unique_count": len(deduped_jobs),
                    "kept_count": len(fresh_jobs),
                    "duplicate_count": duplicate_count,
                    "rejected_count": rejected_count,
                    "seen_count": seen_count,
                    "current_job_title": str(current_job_snapshot.get("current_job_title", "") or ""),
                    "current_job_company": str(current_job_snapshot.get("current_job_company", "") or ""),
                    "search_keywords": search_keywords,
                    "location": normalized_location,
                }
            )

        if len(fresh_jobs) >= minimum_jobs:
            return SearchFilterResult(
                jobs=fresh_jobs,
                search_keywords=search_keywords,
                location=normalized_location,
                target_industry=target_industry,
                company=normalized_company,
                job_level=normalized_level,
                pages_checked=pages_checked,
                jobs_checked=jobs_checked,
                scraped_count=len(collected_jobs),
                duplicate_count=duplicate_count,
                rejected_count=rejected_count,
                seen_count=seen_count,
                no_match_timeout_triggered=runtime_limit_triggered,
            )

        if runtime_limit_triggered:
            break

        if consecutive_empty_pages >= 2:
            break

        if jobs_checked >= no_match_job_limit and not filtered_jobs:
            return SearchFilterResult(
                jobs=[],
                search_keywords=search_keywords,
                location=normalized_location,
                target_industry=target_industry,
                company=normalized_company,
                job_level=normalized_level,
                pages_checked=pages_checked,
                jobs_checked=jobs_checked,
                scraped_count=len(collected_jobs),
                duplicate_count=duplicate_count,
                rejected_count=rejected_count,
                seen_count=seen_count,
                no_match_timeout_triggered=True,
            )

    final_fresh_jobs = [
        job
        for job in filtered_jobs
        if str(job.get("job_id") or job.get("url") or "").strip() not in seen_ids
    ]

    return SearchFilterResult(
        jobs=final_fresh_jobs,
        search_keywords=search_keywords,
        location=normalized_location,
        target_industry=target_industry,
        company=normalized_company,
        job_level=normalized_level,
        pages_checked=pages_checked,
        jobs_checked=jobs_checked,
        scraped_count=len(collected_jobs),
        duplicate_count=duplicate_count,
        rejected_count=rejected_count,
        seen_count=seen_count,
        no_match_timeout_triggered=runtime_limit_triggered or (jobs_checked >= no_match_job_limit and not filtered_jobs),
    )
