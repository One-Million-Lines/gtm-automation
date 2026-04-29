"""Initialize the database from the consolidated schema (db/schema.sql).

Single-shot installer — there are no incremental migrations.
    python setup_database.py

If RECONCILE_THREADS=1 is set, rebuilds conversation threads for every
existing project after the schema is applied.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = str(Path(__file__).parent)
sys.path.append(ROOT_DIR)

from vtutils.confparser import env_config, parse_config
from vtutils.vtlogger import initLog
from db.sqlite_storage import SQLiteStorage

vtlog = initLog("setup_database")


def main() -> None:
    config = env_config(f"{ROOT_DIR}/.env")
    configuration = parse_config("all.ini", config)
    db_path = configuration["sqlite"]["path"]
    if not Path(db_path).is_absolute():
        db_path = str(Path(ROOT_DIR) / db_path)

    vtlog.info("setup_db_start", db_path=db_path)
    storage = SQLiteStorage(db_path)

    schema_file = Path(ROOT_DIR) / "db" / "schema.sql"
    storage.run_script_file(str(schema_file))
    vtlog.info("schema_applied", file=str(schema_file))

    version = storage.get_one("schema_meta", {"key": "version"})
    vtlog.info("setup_db_done", version=version["value"] if version else None)

    if os.environ.get("RECONCILE_THREADS") == "1":
        vtlog.info("reconcile_threads_start")
        from repositories.registry import RepoRegistry
        repos = RepoRegistry(storage)
        from services.conversation_service import rebuild_threads
        projects = repos.projects.find({}, order_by="id ASC", limit=10000)
        total = {"created": 0, "updated": 0, "skipped": 0}
        for project in projects:
            pid = int(project["id"])
            result = rebuild_threads(repos, project_id=pid)
            for k in total:
                total[k] += result.get(k, 0)
            vtlog.info("reconcile_threads_project", project_id=pid, **result)
        vtlog.info("reconcile_threads_done", **total)

    storage.close()


if __name__ == "__main__":
    main()
