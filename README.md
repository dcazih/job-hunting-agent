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
- `src/` – scraper/scoring/storage/memory/email modules
- `api/index.py` – Vercel Python function entrypoint
- `vercel.json` – single-project Vercel config

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
- `POST /api/search/run`
- `GET /api/search/status/{run_id}`
- `POST /api/search/stop/{run_id}`
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

## Runtime storage behavior

In local development, files are read/written under this repo.

On Vercel, writable storage is ephemeral. Runtime data is redirected to:

- `/tmp/job-hunting-agent/data`
- `/tmp/job-hunting-agent/reports`
- `/tmp/job-hunting-agent/profile`
- `/tmp/job-hunting-agent/uploads`

That means uploads/reports/state are not durable across cold starts/instances.
For persistent production data, move storage to external services.

## Notes

- Resume thumbnails are generated from page 1 of uploaded PDFs.
- Search stop is wired to cancel backend runs.
- The frontend uses same-origin API in production and `VITE_API_BASE` in local dev.
