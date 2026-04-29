"""JSON structured logger (lite, adapted from onemillionlines vtutils/vtlogger.py)."""
from __future__ import annotations

import json
import logging
import sys
import traceback
from logging import Logger
from typing import Any

from vtutils.misc import make_json_serializable

LOGGER_NAME = "main"


class VTLogger(Logger):
    def _format(self, msg: Any, **kwargs) -> tuple[dict, dict]:
        log_object: dict = {}
        passed: dict = {}
        if msg and isinstance(msg, str):
            log_object["msg"] = msg
        elif msg is not None:
            log_object["msg"] = str(msg)
        if kwargs:
            if "exc_info" in kwargs:
                passed["exc_info"] = kwargs.pop("exc_info")
            if "extra" in kwargs:
                passed["extra"] = kwargs.pop("extra")
            log_object.update(make_json_serializable(kwargs))
        return log_object, passed

    def _emit(self, level: int, msg: Any, **kwargs) -> None:
        log_object, passed = self._format(msg, **kwargs)
        if level >= logging.ERROR and "exc" in log_object:
            log_object["traceback"] = traceback.format_exc()
        try:
            payload = json.dumps(log_object, ensure_ascii=False, default=str)
        except Exception:
            payload = str(log_object)
        super().log(level, payload, **passed)

    def debug(self, msg: Any = "", *args, **kwargs):  # type: ignore[override]
        self._emit(logging.DEBUG, msg, **kwargs)

    def info(self, msg: Any = "", *args, **kwargs):  # type: ignore[override]
        self._emit(logging.INFO, msg, **kwargs)

    def warning(self, msg: Any = "", *args, **kwargs):  # type: ignore[override]
        self._emit(logging.WARNING, msg, **kwargs)

    def error(self, msg: Any = "", *args, **kwargs):  # type: ignore[override]
        self._emit(logging.ERROR, msg, **kwargs)


logging.setLoggerClass(VTLogger)


def initLog(name: str, level: str = "INFO") -> VTLogger:
    """Initialize the root app logger. Call once per app entrypoint."""
    global LOGGER_NAME
    LOGGER_NAME = name
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '{"ts":"%(asctime)s","lvl":"%(levelname)s","name":"%(name)s","data":%(message)s}'
        ))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger  # type: ignore[return-value]


def getLog(name: str) -> VTLogger:
    """Get a child logger of the app's main logger."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")  # type: ignore[return-value]
