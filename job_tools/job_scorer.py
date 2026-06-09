import os
from typing import List, Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

load_dotenv()


class JobScore(BaseModel):
    score: int = Field(ge=1, le=100)
    recommendation: Literal["apply", "review", "maybe", "ignore"]
    fit_summary: str
    match_reasons: List[str]
    concerns: List[str]
    matched_skills: List[str]
    missing_or_weak_skills: List[str]


def shorten_text(text, max_chars=6000):
    if not text:
        return ""

    text = str(text)

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n[TRUNCATED]"


def get_scoring_model():
    model_name = os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini")

    return ChatOpenAI(
        model=model_name.replace("openai:", ""), temperature=0
    ).with_structured_output(JobScore)


def score_single_job(job, resume_text, preferences_text):
    model = get_scoring_model()

    description = shorten_text(job.get("description", ""), max_chars=6000)
    safe_preferences = str(preferences_text or "").strip()

    prompt = f"""
You are a strict job-matching evaluator.
This is a general job agent, so evaluate any role type fairly and do not assume the job is technical.

Score this job from 1 to 100 based on the candidate's resume and preferences.
If preferences are missing or vague, ignore them and score against the resume only.

Be skeptical. Do not inflate scores.

Scoring guide:
90-100 = excellent match, apply
75-89 = strong match, review
50-74 = borderline match, maybe
0-49 = weak or bad match, ignore

Penalize:
- senior-only jobs when the candidate is not senior
- staff/principal roles
- roles requiring too many years of experience compared to the stated experience
- roles that do not match the user's requested field, company, location, or level
- unpaid work
- unrelated jobs

Reward:
- relevant skills, certifications, or licenses
- matching experience level
- matching location or remote preference
- matching industry or company when the user asked for it
- internships or entry-level roles when the user asked for internships or entry level

Candidate resume:
{resume_text}

Candidate preferences:
{safe_preferences}

Job:
Title: {job.get("title")}
Company: {job.get("company")}
Location: {job.get("location")}
Listed at: {job.get("listed_at")}
URL: {job.get("url")}

Description:
{description}
"""

    result = model.invoke(prompt)

    return result.model_dump()


def score_jobs(jobs, resume_text, preferences_text, is_canceled=None, on_progress=None):
    scored_jobs = []
    total = len(jobs)

    for index, job in enumerate(jobs, start=1):
        if callable(is_canceled) and is_canceled():
            raise RuntimeError("Search was canceled by user.")
        print(
            f"Scoring {index}/{len(jobs)}: {job.get('title')} at {job.get('company')}"
        )

        try:
            score_data = score_single_job(job, resume_text, preferences_text)
        except Exception as error:
            score_data = {
                "score": 1,
                "recommendation": "ignore",
                "fit_summary": "Scoring failed.",
                "match_reasons": [],
                "concerns": [str(error)],
                "matched_skills": [],
                "missing_or_weak_skills": [],
            }

        scored_jobs.append({**job, **score_data})

        if callable(on_progress):
            on_progress(index=index, total=total, job=job, scored_job=scored_jobs[-1])

    scored_jobs.sort(key=lambda item: item.get("score", 0), reverse=True)

    return scored_jobs
