# Telegram Reviews Bot — Deploy on Render (Docker Blueprint)

This repository contains a Telegram bot built with Aiogram 3 and PostgreSQL (asyncpg). The project is prepared for reliable deployment on Render using a Docker-based Blueprint.

## Requirements

- Telegram bot token (BOT_TOKEN)
- Render PostgreSQL instance (DATABASE_URL)
- Optional admin user id (ADMIN_ID)

See `.env.example` for variables.

## Render Blueprint (Docker)

`render.yaml` is configured to deploy a worker with Docker:
- type: worker
- env: docker
- dockerfilePath: ./Dockerfile
- start: uses Dockerfile CMD (`python bot.py`)
- env vars: BOT_TOKEN, DATABASE_URL, ADMIN_ID

### Steps
1. Push this repo to GitHub (done).
2. In Render, click New + -> Blueprint -> choose your repo.
3. Ensure `env: docker` is detected and `Dockerfile` is used.
4. Add environment variables:
   - `BOT_TOKEN` — required
   - `DATABASE_URL` — required (from Render Postgres: External Connection string)
   - `ADMIN_ID` — optional (Telegram numeric ID)
5. Create a Render PostgreSQL instance and copy the `External Connection` string to `DATABASE_URL`.
6. Deploy. The worker will start long-running polling.

## Local run (optional)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# fill BOT_TOKEN and DATABASE_URL
python bot.py
```

## Notes
- The app fails fast if `BOT_TOKEN` or `DATABASE_URL` are missing (clear error).
- `ADMIN_ID` is optional; admin-only features will be hidden if not set.
- Avoid committing local DB files (see `.gitignore`).
- This bot uses long polling; no public HTTP port required on Render.
