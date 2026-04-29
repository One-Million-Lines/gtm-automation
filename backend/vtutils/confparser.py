"""Lightweight config parser. Loads .env + vtconf.d/*.ini.

Sections supported:
  [sqlite]  type=sqlite       → uses SQLITE_DB env var
  [openai]  type=openai       → uses OPENAI_APIKEY env var
"""
from __future__ import annotations

from configparser import ConfigParser
from os.path import expanduser, isfile
from typing import Any

from dotenv import dotenv_values

from vtutils.misc import get_project_root
from vtutils.vtlogger import getLog

mylog = getLog("confparser")
ROOT_DIR = get_project_root()


def env_config(env_path: str) -> dict[str, Any]:
    """Load a .env file into a plain dict."""
    if not isfile(expanduser(env_path)):
        return {}
    return {k: v for k, v in dotenv_values(env_path).items() if v is not None}


def parse_config(filename: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isfile(expanduser(filename)):
        filename = expanduser(f"{ROOT_DIR}/vtconf.d/{filename}")
    if not isfile(filename):
        raise FileNotFoundError(f"Config file not found: {filename}")

    parser = ConfigParser()
    parser.read(filename)

    out: dict[str, Any] = {"env_config": config or {}}

    for section in parser.sections():
        section_type = parser.get(section, "type", fallback=section)
        section_data = dict(parser.items(section))

        if section_type == "sqlite":
            db_path = (config or {}).get("SQLITE_DB") or section_data.get("path") or "data/gtm.sqlite"
            out[section] = {"path": db_path, "type": "sqlite"}

        elif section_type == "openai":
            out[section] = {
                "type": "openai",
                "api_key": (config or {}).get("OPENAI_APIKEY", ""),
            }

        else:
            out[section] = section_data

    return out
