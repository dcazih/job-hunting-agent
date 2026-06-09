# Job Hunting Agent

Job search app with a React frontend and a FastAPI API.

## What it does

- Upload and manage multiple resumes (select active resume)
- Run a job search pipeline
- Score jobs against resume + preferences
- Generate and browse reports (top jobs + remaining jobs)
- Email latest report
- Persist feedback/memory

## Project structure

- `frontend/` – Vite + React client UI
- `backend/` – FastAPI routes + orchestration
- `job_tools/` – scraper/scoring/storage/memory/email modules
- `api/index.py` – Vercel Python function entrypoint
- `vercel.json` – single-project Vercel config
- `.github/workflows/daily-scheduler.yml` – GitHub Actions poller for the daily scheduler

## API routes

Core routes used by the frontend:

- `GET /api/health`
- `POST /api/resume/upload`
- `GET /api/resume/uploads`
- `POST /api/resume/uploads/{upload_name}/select`
- `DELETE /api/resume/uploads/{upload_name}`
- `GET /api/resume/uploads/{upload_name}/thumbnail`
- `GET /api/preferences`
- `POST /api/preferences`
- `POST /api/chat`
- `GET /api/chat/status?session_id=...`
- `POST /api/chat/stop?session_id=...`
- `GET /api/cron`
- `GET /api/reports/latest`
- `GET /api/reports`
- `GET /api/reports/item?report_path=...`
- `DELETE /api/reports/item?report_path=...`
- `POST /api/reports/latest/email`
- `POST /api/feedback`

## Local development

### Requirements

- Python 3.11+
- Node 18+

### Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:8000 npm run dev
```

## Environment variables

Set these for backend/API runtime:

- `OPENAI_API_KEY`
- `AGENT_MODEL` (optional)
- `EMAIL_FROM`
- `EMAIL_TO`
- `GMAIL_APP_PASSWORD`

Optional:

- `APP_RUNTIME_DIR` (override runtime storage root)

## Deploy on Vercel (single project)

This repo is configured so frontend and API deploy together in one Vercel project.

1. Push to GitHub
2. Import the repo in Vercel
3. Keep root directory at repo root
4. Add environment variables in Vercel
5. Deploy

`vercel.json` already defines:

- frontend build command/output
- Python function entry at `api/index.py`

Connect a Postgres database to the Vercel project and expose either:

- `DATABASE_URL`
- `POSTGRES_URL`

The database is required for durable resumes, reports, search progress, memory, and scheduler state across Vercel instances.

Vercel cron is disabled in this repo. The daily scheduler is triggered by GitHub Actions instead.

## GitHub Actions scheduler setup

This repo includes `.github/workflows/daily-scheduler.yml`, which runs every 5 minutes and calls the backend cron endpoint.

Set these GitHub repository secrets:

- `BACKEND_URL` — your deployed backend base URL, for example `https://your-app.vercel.app`
- `CRON_SECRET` — the same secret value you set in your backend environment variables

Set this backend environment variable in Vercel:

- `CRON_SECRET` — a random secret string used to authorize scheduler requests

How it works:

- GitHub Actions sends `Authorization: Bearer <CRON_SECRET>` to `GET /api/cron`
- the backend verifies the header and checks whether the saved schedule is due
- if due, it runs the search pipeline using the shared scheduler settings

## Runtime storage behavior

In local development, files are read/written under this repo.

On Vercel, writable storage is ephemeral and is used only as a temporary cache. Runtime files are redirected to:

- `/tmp/job-hunting-agent/data`
- `/tmp/job-hunting-agent/reports`
- `/tmp/job-hunting-agent/profile`
- `/tmp/job-hunting-agent/uploads`

When `DATABASE_URL` or `POSTGRES_URL` is configured, durable resumes, reports, search progress, memory, and scheduler state are stored in Postgres and survive refreshes, cold starts, and different Vercel instances.

## Notes

- Resume thumbnails are generated from page 1 of uploaded PDFs.
- Search stop is wired to cancel backend runs.
- The frontend uses same-origin API in production and `VITE_API_BASE` in local dev.
- User-initiated searches go through `POST /api/chat`; there is no separate manual search endpoint.
- On Vercel, the in-process scheduler is disabled and the daily cron path is used instead.
