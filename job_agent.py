import os
from datetime import datetime
from dotenv import load_dotenv

from langchain.agents import create_agent

from job_tools import (
    check_report_sent_today,
    load_candidate_profile,
    scrape_linkedin_jobs_tool,
    filter_seen_jobs,
    score_jobs_against_profile,
    build_daily_report,
    send_email_report,
    save_reported_jobs,
    mark_report_complete_today,
)

from memory_tools import (
    remember_job_preference,
    remember_company_feedback,
    remember_role_feedback,
    remember_job_feedback,
    read_agent_memory,
    forget_memory_item,
)


load_dotenv()


SYSTEM_PROMPT = """
You are Dmitri's daily software engineering job-search agent.

Your goal:
Find promising software engineering jobs, score them against Dmitri's resume and preferences,
create a daily report, and email it.

Rules:
1. First check whether today's report has already been sent.
2. If already sent, stop.
3. Load the candidate profile.
4. Search LinkedIn guest jobs.
5. Start with "software engineer" in "United States".
6. If fewer than 5 promising jobs score 80 or higher, try related searches:
   - software engineer intern
   - new grad software engineer
   - backend engineer
   - full stack engineer
   - react native developer
   - computer vision engineer
7. Remove jobs already seen in previous reports.
8. Score jobs from 1 to 100.
9. Build a Markdown report with:
   - top 5 best matches first
   - then the remaining jobs
   - scores
   - links
   - match reasons
   - concerns
10. Email the report.
11. Save reported job IDs.
12. Mark today's report complete.

Be skeptical.
Do not pretend weak jobs are good.
If the search results are poor, say that in the report.

Memory rules:
- When the user says "remember", "from now on", "going forward", "note that", or gives a lasting job-search preference, use the appropriate memory tool.
- Before scoring jobs, call read_agent_memory and use saved preferences/feedback along with resume.txt and preferences.txt.
- Do not claim you remembered something unless you successfully called a memory tool.
- If the user asks what you remember, call read_agent_memory.
- If the user asks you to forget something, call forget_memory_item if they provide an ID. If they do not provide an ID, show the relevant memories first.
"""


def create_job_agent():
    tools = [
        check_report_sent_today,
        load_candidate_profile,
        read_agent_memory,
        remember_job_preference,
        remember_company_feedback,
        remember_role_feedback,
        remember_job_feedback,
        forget_memory_item,
        scrape_linkedin_jobs_tool,
        filter_seen_jobs,
        score_jobs_against_profile,
        build_daily_report,
        send_email_report,
        save_reported_jobs,
        mark_report_complete_today,
    ]

    model = os.getenv("AGENT_MODEL", "openai:gpt-4.1-mini")

    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )

    return agent


def run_daily_job_agent():
    agent = create_job_agent()

    today = datetime.now().strftime("%Y-%m-%d")

    result = agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": f"Run Dmitri's daily software engineering job search for {today}."
            }
        ]
    })

    return result


if __name__ == "__main__":
    result = run_daily_job_agent()

    print("Agent finished.")
    print(result)