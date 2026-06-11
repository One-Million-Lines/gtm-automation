# GTM Automation

GTM Automation is a full-stack workflow app for managing go-to-market operations across ICPs, companies, contacts, signals, leads, outreach, sends, replies, inbox workflows, and pipeline runs. It combines a React frontend, a FastAPI backend, SQLite persistence, optional LLM-powered drafting and classification, and deployment assets for Docker or traditional server setups.

## What it does

It provides an authenticated workspace for running and reviewing GTM workflows, from project setup through outreach execution and reply handling.

## Why it exists

GTM work often spans too many disconnected tools: spreadsheets for ICPs, separate systems for leads, and manual switching between sending, replies, and performance review. This project brings those flows into one app with project-scoped access and configurable automation.

## Features

- Register, log in, and manage authenticated users
- Project-scoped workflows and access control
- ICP, company, contact, signal, lead, outreach, send, reply, and feedback pages
- Pipeline runs and dashboard views
- Lead inbox and reasoning views
- Optional LLM reply drafter and classifier with fallback behavior
- Configurable email sending via fake, SMTP, SendGrid, or Postmark providers
- Structured logging, rate limiting, and optional Sentry integration
- Docker Compose, nginx, and systemd deployment scaffolding in `_ops/`

## How it works

1. The frontend authenticates users and injects bearer tokens into API requests.
2. The backend protects most routes with JWT auth and keeps data in SQLite.
3. Startup installs default adapters and can enable LLM-backed drafting and classification based on environment variables.
4. Pipeline routes manage ingestion, enrichment, lead processing, outreach, sending, replies, and related GTM views.
5. `_ops/` contains Docker and deployment assets for running the app outside local development.

## Tech stack

- React
- TypeScript
- Vite
- Tailwind CSS
- TanStack Query
- FastAPI
- SQLite
- LiteLLM
- SMTP / SendGrid / Postmark integrations
- Docker Compose

## Project structure

```text
frontend/
  src/
    pages/           dashboard, pipeline, outreach, replies, feedback, tuning, inbox
    state/           auth and project state
    components/      app shell and shared UI
backend/
  api_*.py           FastAPI route modules
  pipeline/          pipeline runner and modules
  services/          LLM, email, and ingestion services
  repositories/      SQLite-backed data access
  setup_database.py  schema setup and seed/bootstrap helpers
  pip_requirements.txt
_ops/
  docker-compose.yml
  Dockerfile.backend
  Dockerfile.frontend
  deploy.sh
```

## Getting started

```bash
git clone <repo-url>
cd gtm-automation
```

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r pip_requirements.txt
cp .env.example .env
python setup_database.py
export PYTHONPATH=$PYTHONPATH:.
uvicorn main:app --host 127.0.0.1 --port 5214 --reload
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open:

- Frontend: `http://localhost:5314`
- API: `http://127.0.0.1:5214`
- API docs: `http://127.0.0.1:5214/docs`

The first registered user becomes an admin. After bootstrapping the first account, set `ALLOW_REGISTRATION=false` in `backend/.env`.

## Configuration

Frontend:

```env
VITE_API_BASE=http://127.0.0.1:5214
```

Backend:

```env
APP_PORT=5214
APP_HOST=0.0.0.0
APP_ENV=development
SQLITE_DB=data/gtm.sqlite
CORS_ORIGINS=http://localhost:5314,http://127.0.0.1:5314
JWT_SECRET=change_me_to_a_long_random_string
JWT_EXPIRES_HOURS=24
ALLOW_REGISTRATION=true
RATE_LIMIT_PER_MINUTE=120
EMAIL_PROVIDER=fake
OPENAI_APIKEY=
ANTHROPIC_API_KEY=
GOOGLE_GENAI_APIKEY=
VERTEXAI_APIKEY=
USE_LLM_DRAFTER=true
USE_LLM_CLASSIFIER=true
LLM_REPLY_MODEL=gpt-4o-mini
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
SMTP_FROM=
SENDGRID_API_KEY=
POSTMARK_SERVER_TOKEN=
SENTRY_DSN=
```

Use `backend/.env.example` for the full documented set of backend options.

## Usage

1. Start the backend and frontend.
2. Register the first user and create a project.
3. Work through the GTM flow across ICPs, companies, contacts, signals, leads, outreach, sends, and replies.
4. Use pipeline runs and feedback/tuning pages to review results.
5. Enable LLM and email-provider settings only when you want live drafting or message delivery.

## Development

```bash
cd frontend && npm run dev
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm run preview
cd backend && python setup_database.py
cd _ops && docker compose up -d --build
```

There is currently no dedicated automated test command in the repository.

## Roadmap

- Add automated API and frontend tests
- Expand documentation for each pipeline stage
- Add stronger production hardening guidance around registration and secrets
- Add richer reporting around runs, sends, and replies

## Contributing

This project is public and open for collaboration. If you’re interested in contributing, improving the project, or discussing ideas, feel free to reach out.

LinkedIn: https://linkedin.com/in/alexrada

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Open a pull request

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE).
