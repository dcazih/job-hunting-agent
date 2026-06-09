from __future__ import annotations

import os
import re

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from backend.agent_factory import create_job_agent
from pathlib import Path

from backend.agent import (
    cancel_search_run,
    create_search_run,
    clear_chat_active_run_id,
    clear_current_run_id,
    clear_current_resume_display_name,
    get_chat_active_run_id,
    get_chat_messages,
    clear_chat_messages,
    get_search_run,
    get_search_schedule,
    delete_uploaded_resume,
    delete_report_by_path,
    email_latest_report,
    get_latest_report,
    get_report_by_path,
    get_preferences,
    get_resume_status,
    list_uploaded_resumes,
    list_reports,
    save_feedback,
    save_preferences,
    save_search_schedule,
    save_uploaded_resume,
    save_chat_messages,
    set_chat_active_run_id,
    set_current_time_zone,
    clear_current_time_zone,
    set_current_run_id,
    set_current_resume_display_name,
    get_chat_session_lock,
    run_daily_schedule_cron,
    start_scheduler,
    stop_scheduler,
    set_active_uploaded_resume,
    UPLOAD_THUMBNAILS_DIR,
)
from backend.schemas import EmailLatestRequest, FeedbackRequest, PreferencesRequest, ScheduleRequest, ChatRequest


app = FastAPI(title="Job Hunting Agent API", version="0.1.0")
CHAT_AGENT = create_job_agent()

TARGET_INDUSTRY_PATTERNS = [
    ("software engineer", ["software engineer", "software engineering"]),
    ("frontend", ["frontend", "front end"]),
    ("backend", ["backend", "back end"]),
    ("cybersecurity", ["cybersecurity", "cyber security", "security engineer", "security"]),
    ("data scientist", ["data scientist", "data science", "machine learning", "ml engineer"]),
    ("data analyst", ["data analyst", "analytics analyst"]),
    ("devops", ["devops", "sre", "site reliability", "platform engineer"]),
    ("product manager", ["product manager", "product management"]),
    ("qa engineer", ["qa engineer", "quality assurance", "test engineer"]),
    ("mobile developer", ["mobile developer", "mobile development", "ios", "android"]),
]

JOB_LEVEL_PATTERNS = [
    ("junior", ["junior", "entry level", "entry-level", "jr", "new grad", "graduate"]),
    ("intermediate", ["intermediate", "mid level", "mid-level", "mid"]),
    ("senior", ["senior", "lead", "staff", "principal", "sr"]),
]


def _extract_search_hints(message: str) -> dict[str, str]:
    text = str(message or "")
    lower = text.lower()

    target_industry = ""
    for canonical, variants in TARGET_INDUSTRY_PATTERNS:
        if any(variant in lower for variant in variants):
            target_industry = canonical
            break

    job_level = ""
    for canonical, variants in JOB_LEVEL_PATTERNS:
        if any(re.search(rf"\b{re.escape(variant)}\b", lower) for variant in variants):
            job_level = canonical
            break

    company = ""
    company_match = re.search(
        r"\b(?:at|for|with)\s+([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,3})",
        text,
    )
    if company_match:
        candidate = company_match.group(1).strip(" ,.;:!?")
        if candidate.lower() not in {"startups", "startup", "remote", "united states"}:
            company = candidate

    location = ""
    if re.search(r"\bremote\b", lower):
        location = "Remote, United States"

    hints: dict[str, str] = {}
    if target_industry:
        hints["target_industry"] = target_industry
    if company:
        hints["company"] = company
    if job_level:
        hints["job_level"] = job_level
    if location:
        hints["location"] = location
    return hints

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_scheduler() -> None:
    if os.getenv("VERCEL") or os.getenv("DISABLE_INPROCESS_SCHEDULER"):
        return
    start_scheduler()


@app.on_event("shutdown")
def _shutdown_scheduler() -> None:
    stop_scheduler()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return save_uploaded_resume(file.filename, content)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/preferences")
def read_preferences() -> dict:
    return get_preferences()


@app.get("/api/resume/status")
def read_resume_status() -> dict:
    return get_resume_status()


@app.get("/api/resume/uploads")
def read_resume_uploads() -> dict:
    return list_uploaded_resumes()


@app.delete("/api/resume/uploads/{upload_name}")
def remove_resume_upload(upload_name: str) -> dict:
    try:
        return delete_uploaded_resume(upload_name)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/resume/uploads/{upload_name}/select")
def select_resume_upload(upload_name: str) -> dict:
    try:
        return set_active_uploaded_resume(upload_name)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/resume/uploads/{upload_name}/thumbnail")
def get_resume_upload_thumbnail(upload_name: str):
    safe_name = Path(upload_name).name
    thumb_path = UPLOAD_THUMBNAILS_DIR / f"{Path(safe_name).stem}.png"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Resume thumbnail not found")
    return FileResponse(thumb_path, media_type="image/png")


@app.post("/api/preferences")
def write_preferences(payload: PreferencesRequest) -> dict:
    try:
        return save_preferences(payload.preferences)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/schedule")
def read_schedule() -> dict:
    return get_search_schedule()


@app.post("/api/schedule")
def write_schedule(payload: ScheduleRequest) -> dict:
    try:
        return save_search_schedule(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/cron")
def cron_job(request: Request) -> dict:
    cron_secret = os.getenv("CRON_SECRET", "").strip()
    if cron_secret:
        auth_header = str(request.headers.get("authorization", "") or "").strip()
        if auth_header != f"Bearer {cron_secret}":
            raise HTTPException(status_code=401, detail="Unauthorized")
    return run_daily_schedule_cron()


@app.get("/api/reports/latest")
def latest_report() -> dict:
    return get_latest_report()


@app.get("/api/reports")
def reports() -> dict:
    return list_reports()


@app.get("/api/reports/item")
def report_item(report_path: str) -> dict:
    try:
        return get_report_by_path(report_path)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/reports/item")
def delete_report(report_path: str) -> dict:
    try:
        return delete_report_by_path(report_path)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/reports/latest/email")
def email_report(payload: EmailLatestRequest | None = None) -> dict:
    to_email = payload.to_email if payload else ""
    return email_latest_report(to_email=to_email)


@app.post("/api/feedback")
def feedback(payload: FeedbackRequest) -> dict:
    return save_feedback(
        job_id=payload.job_id,
        feedback=payload.feedback,
        reason=payload.reason,
        title=payload.title,
        company=payload.company,
    )


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict:
    user_message = payload.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    session_id = str(payload.session_id or "default").strip() or "default"

    def _extract_report(messages: list) -> dict | None:
        for message in reversed(messages):
            content = getattr(message, "content", None)
            if isinstance(content, dict):
                if content.get("report") or content.get("top_jobs") or content.get("remaining_jobs"):
                    return content
            if isinstance(content, str):
                text = content.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except Exception:
                    continue
                if isinstance(parsed, dict) and (parsed.get("report") or parsed.get("top_jobs") or parsed.get("remaining_jobs")):
                    return parsed
        return None

    run_id = create_search_run()
    set_chat_active_run_id(session_id, run_id)
    set_current_run_id(run_id)
    set_current_resume_display_name(payload.resume_display_name)
    set_current_time_zone(payload.timezone)
    assistant_content = ""
    messages: list = []
    try:
        history = get_chat_messages(session_id)
        conversation = list(history)
        if payload.resume_display_name:
            conversation = [
                {
                    "role": "system",
                    "content": f"Active resume already selected in the UI: {payload.resume_display_name}. Do not ask the user to upload a resume before searching.",
                }
            ] + conversation
        search_hints = _extract_search_hints(user_message)
        if search_hints:
            hint_bits = [f"{key}={value}" for key, value in search_hints.items()]
            conversation.append(
                {
                    "role": "system",
                    "content": (
                        "Parsed search hints from the latest user message: "
                        + "; ".join(hint_bits)
                        + ". Treat any non-empty hint as authoritative for the search tool call. "
                        "Do not reuse remembered search fields when the user explicitly provided a value. "
                        "Do not ask the user to choose between the latest explicit target industry and any remembered one."
                    ),
                }
            )
        conversation.append({"role": "user", "content": user_message})
        result = CHAT_AGENT.invoke({"messages": conversation})
        messages = result.get("messages", [])
        assistant_content = str(result)
        if messages:
            assistant_content = messages[-1].content
        save_chat_messages(
            session_id,
            history
            + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_content},
            ],
        )
    except RuntimeError as error:
        if "Search was canceled by user." not in str(error):
            raise
        assistant_content = "Stopped."
        messages = []
    finally:
        clear_chat_active_run_id(session_id)
        clear_current_run_id()
        clear_current_resume_display_name()
        clear_current_time_zone()

    normalized_assistant = " ".join(str(assistant_content or "").split()).lower()
    if normalized_assistant in {"load failed", "request failed", "failed"}:
        run = get_search_run(run_id)
        if run:
            run_result = run.result or {}
            failure_message = str(run.error or run_result.get("message") or "").strip()
            if not failure_message:
                failure_message = {
                    "missing_resume": "Please upload or select a resume/profile before I can search.",
                    "missing_target_industry": "Specify a target industry before searching.",
                }.get(str(run_result.get("status") or "").strip(), "")
            if failure_message:
                assistant_content = failure_message

    response: dict = {"assistant_message": assistant_content}
    report = _extract_report(messages)
    if report is not None:
        response["report"] = report
    return response


@app.post("/api/chat/reset")
def reset_chat(session_id: str = "default") -> dict:
    normalized_session_id = str(session_id or "default").strip() or "default"
    clear_chat_messages(normalized_session_id)
    clear_chat_active_run_id(normalized_session_id)
    return {"status": "ok"}


@app.post("/api/chat/stop")
def stop_chat(session_id: str = "default") -> dict:
    run_id = get_chat_active_run_id(session_id)
    if not run_id:
        return {"status": "idle"}
    return cancel_search_run(run_id)


@app.get("/api/chat/status")
def chat_status(session_id: str = "default") -> dict:
    run_id = get_chat_active_run_id(session_id)
    if not run_id:
        return {"active": False, "run": None}
    return {"active": True, "run": get_search_run(run_id)}
