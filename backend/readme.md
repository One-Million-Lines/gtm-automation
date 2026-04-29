# GTM Automation — Backend

## Stack
- Python 3.11+
- FastAPI + Uvicorn
- SQLite (via reusable `SQLiteStorage` class)
- Custom config (`.env` + `vtconf.d/all.ini`)
- JSON structured logging (`vtutils.vtlogger`)

## Layout
```
backend/
├── main.py                 # FastAPI app entry
├── api_shared.py           # config, logger, SQLite singleton
├── api_health.py           # /health endpoints
├── setup_database.py       # runs db/schema.sql (idempotent)
├── pip_requirements.txt
├── .env.example
├── vtconf.d/all.ini        # [sqlite] [openai]
├── vtutils/                # reusable helpers
│   ├── misc.py             # paths, json, normalize_domain/email, slugify
│   ├── vtlogger.py         # JSON logger
│   ├── confparser.py       # env + ini loader
│   └── vtfiles.py          # file/csv/json helpers
└── db/
    ├── sqlite_storage.py   # reusable SQLite class (CRUD + upsert + scripts)
    └── schema.sql          # filled in Phase 1
```

## Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r pip_requirements.txt
cp .env.example .env
python setup_database.py
python main.py            # http://localhost:5220
```

## Health
- `GET /health`     → `{status, db, env}`
- `GET /health/db`  → db path + schema version

## Reusable classes
- `SQLiteStorage` — `get_one/get_many/insert_one/insert_many/upsert_one/update_one/delete_one/count/exists/execute/fetchone/fetchall/run_script_file`
- `vtfiles` — `read/write_text/json/csv_dicts`, `ensure_dir`, `list_files`
- `vtutils.misc` — `normalize_domain`, `normalize_email`, `to_json`, `from_json`, `now_iso`, `slugify`
