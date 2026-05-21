# Topic Fanout Tool (`info-site-kw-research-cluster`)

Keyword research and niche-site architecture planning. Given one seed keyword,
it produces a clustered content map (silos → articles → keywords) and a proposed
site architecture for a niche authority site.

The full specification is the PRD: [`docs/topic-fanout-prd-v1_7.md`](docs/topic-fanout-prd-v1_7.md).
Persistent build context and locked decisions live in [`CLAUDE.md`](CLAUDE.md).

> This repo was reset on 2026-05-21. The previous 12-phase implementation was
> archived for human reference only and is not a reference for this build.

## Monorepo layout

```
backend/    FastAPI (Python 3.11) — deploys to Railway service `info-site-kw-research-cluster`
frontend/   React + Vite + TypeScript — deploys to Netlify from /frontend
supabase/   SQL migrations; all tables isolated under the `fanout` schema
docs/       The PRD (source of truth)
```

## Build status

Built milestone-by-milestone (PRD §15.1). **Current: M1 — Foundation.**

M1 delivers: Supabase Auth sign-in, the `fanout` schema with `user_profiles`,
`projects`, `sessions`, `workspace_settings` (RLS enforced), auto-created Scratch
project on first login, a minimal FastAPI service with `/healthz` + structured
logging, and a minimal React app (login + empty project list).

## One-time Supabase setup (required for M1)

The app's tables live under the `fanout` schema. PostgREST only serves schemas
that are **exposed**. In the Supabase dashboard for the AR-Internal-Tools project:

> **Settings → API → Exposed schemas** → add `fanout` → save.

Without this, the backend can authenticate users but cannot read/write the
`fanout` tables via the Supabase client.

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in SUPABASE_* values
uvicorn app.main:app --reload
pytest
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # fill in VITE_* values
npm run dev
npm run build
```

## Deployment

- **Backend → Railway**: service `info-site-kw-research-cluster` in project
  `AR Tools`, root directory `/backend`, Dockerfile build. Inherits Supabase /
  OpenAI / Anthropic / DataForSEO keys from the project; set
  `SUPABASE_ANON_KEY` and `CORS_ALLOW_ORIGINS` on the service.
- **Frontend → Netlify**: base directory `frontend/`, build `npm run build`,
  publish `frontend/dist`. Set `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`,
  `VITE_SUPABASE_ANON_KEY`.
