# Job Hunting Agent UI + API MVP

This project now includes:

- `backend/`: FastAPI API layer around your existing Python agent tools
- `frontend/`: React dark chat UI with collapsible reports sidebar, resume upload, search, and report/email actions
- existing `src/`: scraper, scorer, emailer, memory, and storage logic

## Architecture

Frontend (React)
-> FastAPI backend (`backend/main.py`)
-> Controlled search pipeline (`backend/agent.py`)
-> Existing tools in `src/`
-> Local storage (`profile/`, `reports/`, `data/`, `uploads/`)

## API Endpoints

- `POST /api/resume/upload`
- `GET /api/preferences`
- `POST /api/preferences`
- `POST /api/search/run`
- `GET /api/search/status/{run_id}`
- `GET /api/reports/latest`
- `GET /api/reports`
- `GET /api/reports/item?report_path=...`
- `POST /api/reports/latest/email`
- `POST /api/feedback`

## Search Flow

`Search` in chat triggers a controlled backend flow:

1. Load resume + preferences
2. Read saved memory
3. Scrape LinkedIn jobs
4. Filter previously reported jobs
5. AI-score jobs
6. Build markdown report (top 5 first)
7. Save report + seen jobs
8. Return result to UI

## Run Backend

```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Set frontend API base if needed:

```bash
VITE_API_BASE=http://localhost:8000 npm run dev
```

## Deploy On Vercel (Single Project: UI + API)

This repo is now configured to deploy as one Vercel project:

- `frontend/` builds the static React app
- `api/index.py` serves FastAPI routes (`/api/*`)

### Required Vercel Environment Variables

- `OPENAI_API_KEY`
- `AGENT_MODEL` (optional, defaults in code)
- `EMAIL_FROM`
- `EMAIL_TO`
- `GMAIL_APP_PASSWORD`

### Deploy Steps

1. Push to GitHub.
2. Import repo in Vercel.
3. Keep project root at repo root.
4. Vercel will use `vercel.json`:
   - build command: `cd frontend && npm ci && npm run build`
   - output directory: `frontend/dist`
   - Python function entry: `api/index.py`
5. Set env vars in Vercel Project Settings.

### Important Runtime Note

On Vercel, filesystem writes are only safe in `/tmp`.
This project now auto-switches runtime storage to `/tmp/job-hunting-agent` when `VERCEL` is set, so uploads/reports/data work in serverless runtime.
Data is still ephemeral across cold starts/instances, so for production persistence you should move `data/`, `reports/`, `uploads/`, and `profile/` to external storage/DB.

## Notes

- Resume upload writes canonical active resume to `profile/resume.pdf` and refreshes `profile/resume.txt`.
- Latest run snapshot is saved to `data/latest_run.json` and `reports/*.json` for structured UI rendering.
- Email sending uses your existing `.env` (`EMAIL_FROM`, `EMAIL_TO`, `GMAIL_APP_PASSWORD`).
