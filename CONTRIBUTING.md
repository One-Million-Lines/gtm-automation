# Contributing

Thanks for your interest in contributing.

## Local setup

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

## Making changes

- Keep backend route and service changes documented in the README
- Use `backend/.env.example` as the source of truth for documented config
- Run frontend build and lint commands before opening a pull request

## Pull requests

1. Fork the repository
2. Create a branch for your change
3. Make your changes
4. Open a pull request with context about the GTM flow you changed

## Reporting issues

Open a GitHub issue with reproduction steps, the affected pipeline stage, and any relevant logs.
