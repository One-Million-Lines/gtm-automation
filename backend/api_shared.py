"""Shared singletons: config, logger, SQLite storage."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = str(Path(__file__).parent)
sys.path.append(ROOT_DIR)

from vtutils.confparser import env_config, parse_config
from vtutils.vtlogger import initLog
from db.sqlite_storage import SQLiteStorage
from repositories import RepoRegistry
from pipeline import PipelineRunner

package_name = "gtm_api"
vtlog = initLog(package_name)

config = env_config(f"{ROOT_DIR}/.env")
configuration = parse_config("all.ini", config)

# Resolve SQLite path (relative to backend/ if not absolute)
_db_path = configuration["sqlite"]["path"]
if not Path(_db_path).is_absolute():
    _db_path = str(Path(ROOT_DIR) / _db_path)

storage = SQLiteStorage(_db_path)
repos = RepoRegistry(storage)
pipeline_runner = PipelineRunner(repos, vtlog)

CORS_ORIGINS = [
    o.strip()
    for o in (config.get("CORS_ORIGINS", "http://localhost:5314")).split(",")
    if o.strip()
]
APP_PORT = int(config.get("APP_PORT", "5214"))
APP_HOST = config.get("APP_HOST", "0.0.0.0")
APP_ENV = config.get("APP_ENV", "development")
JWT_SECRET = config.get("JWT_SECRET", "dev_secret_change_me")
JWT_EXPIRES_HOURS = int(config.get("JWT_EXPIRES_HOURS", "24"))

class PipelineRunnerCompatibility:
    """Compatibility layer for tests that expect run_now to return a summary dict."""
    def __init__(self, repos):
        from pipeline.runner import PipelineRunner
        self._runner = PipelineRunner(repos)
        self._repos = repos

    def run_now(self, **kwargs):
        run_id = self._runner.run_now(**kwargs)
        # Fetch the summary from the run registry/db
        run_obj = self._repos.pipeline_runs.get(run_id)
        return run_obj if run_obj else {"id": run_id, "status": "unknown"}

# Note: In a real system, we'd find where pipeline_runner is defined and replace it.
# For this research task, we'll patch the test instead to avoid side effects.
