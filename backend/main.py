from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from threading import Lock
from run_daily_agent import create_job_agent
from pathlib import Path

from backend.agent import (
    cancel_search_run,
    create_search_run,
    delete_uploaded_resume,
    delete_report_by_path,
    email_latest_report,
    execute_search_run,
    get_latest_report,
    get_report_by_path,
    get_preferences,
    get_resume_status,
    get_search_run,
    list_uploaded_resumes,
    list_reports,
    save_feedback,
    save_preferences,
    save_uploaded_resume,
    set_active_uploaded_resume,
    UPLOAD_THUMBNAILS_DIR,
)
from backend.schemas import EmailLatestRequest, FeedbackRequest, PreferencesRequest, SearchRunRequest
from backend.schemas import ChatRequest


app = FastAPI(title="Job Hunting Agent API", version="0.1.0")
CHAT_LOCK = Lock()
CHAT_AGENT = create_job_agent()
CHAT_MESSAGES: list[dict] = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/api/search/run")
def run_search(payload: SearchRunRequest, background_tasks: BackgroundTasks) -> dict:
    run_id = create_search_run()
    background_tasks.add_task(
        execute_search_run,
        run_id,
        keywords=payload.keywords,
        location=payload.location,
        pages=payload.pages,
    )

    return {
        "status": "started",
        "run_id": run_id,
    }


@app.get("/api/search/status/{run_id}")
def search_status(run_id: str) -> dict:
    run = get_search_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return run


@app.post("/api/search/stop/{run_id}")
def stop_search(run_id: str) -> dict:
    try:
        return cancel_search_run(run_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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

    with CHAT_LOCK:
        CHAT_MESSAGES.append({"role": "user", "content": user_message})
        result = CHAT_AGENT.invoke({"messages": CHAT_MESSAGES})
        messages = result.get("messages", [])
        assistant_content = str(result)
        if messages:
            assistant_content = messages[-1].content
        CHAT_MESSAGES.append({"role": "assistant", "content": assistant_content})

    return {"assistant_message": assistant_content}
