"""
Module used to configure and initialize the logging facility.
Outputs to stdout. initLog needs to be called once per application.

Example usage:
Main module:
    vtlog = initLog("my_app")
    vtlog.debug("test")
    vtlog.info("reached checkpoint")
    vtlog.error("Kaboom", exc=e)

Subsequent modules:
    vtlog = getLog("my_module")   # displays as myapp.my_module
    vtlog.error("Error!", exc=e)
"""
from __future__ import annotations

import datetime
import json
import logging
import logging.handlers
import sys
import traceback
from logging import Logger
from typing import Any

from vtutils.misc import make_json_serializable

LOGGER_NAME = "main"
FILTERS: list = []


class VTLogger(Logger):

    def __init__(self, name: str) -> None:
        super().__init__(name)

    def _remove_curly(self, msg: str) -> str:
        """Strip wrapping { } so the message embeds cleanly inside the log line JSON."""
        if msg and msg.startswith("{"):
            msg = msg[1:]
        if msg and msg.endswith("}"):
            msg = msg[:-1]
        return msg

    def _format_msg(self, msg: Any, *args: Any, **kwargs: Any) -> tuple[dict, dict]:
        log_object: dict = {}
        passed: dict = {}
        try:
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
        except Exception as e:
            log_object = {"msg": repr(msg), "fmt_err": str(e)}
        return log_object, passed

    def debug(self, msg: Any = "", *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        log_object, passed = self._format_msg(msg, *args, **kwargs)
        try:
            payload = self._remove_curly(json.dumps(log_object, ensure_ascii=False, default=str))
        except Exception:
            payload = repr(log_object)
        super().debug(payload, *args, **passed)

    def info(self, msg: Any = "", *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        log_object, passed = self._format_msg(msg, *args, **kwargs)
        try:
            payload = self._remove_curly(json.dumps(log_object, ensure_ascii=False, default=str))
        except Exception:
            payload = repr(log_object)
        super().info(payload, *args, **passed)

    def warning(self, msg: Any = "", *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        log_object, passed = self._format_msg(msg, *args, **kwargs)
        try:
            payload = self._remove_curly(json.dumps(log_object, ensure_ascii=False, default=str))
        except Exception:
            payload = repr(log_object)
        super().warning(payload, *args, **passed)

    def error(self, msg: Any = "", *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        log_object, passed = self._format_msg(msg, *args, **kwargs)
        if "exc" in log_object:
            log_object["err_type"] = type(log_object["exc"]).__name__
            log_object["err_details"] = repr(log_object["exc"])
            log_object["traceback"] = traceback.format_exc()
            del log_object["exc"]
        else:
            log_object["err_type"] = "custom"
        try:
            super().error(
                self._remove_curly(json.dumps(log_object, ensure_ascii=False, default=str)),
                *args,
                **passed,
            )
        except Exception as e:
            super().error("error_format_log original=%r fmt_err=%s" % (log_object, e))


class _VT4Formatter(logging.Formatter):
    converter = datetime.datetime.fromtimestamp  # type: ignore[assignment]

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = self.converter(record.created)
        t = ct.strftime("%Y-%m-%dT%H:%M:%S")
        return "%s.%03d" % (t, record.msecs)


def _has_stdout_handler(logger: logging.Logger) -> bool:
    return any(getattr(h, "_vtlogger_stdout", False) for h in logger.handlers)


logging.setLoggerClass(VTLogger)


def initLog(name: str, level: str = "INFO") -> VTLogger:
    """Initialize the root app logger. Call once per app entrypoint."""
    global LOGGER_NAME, FILTERS
    LOGGER_NAME = name
    logging.setLoggerClass(VTLogger)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not _has_stdout_handler(logger):
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        formatter = _VT4Formatter(
            '{"ts": "%(asctime)s", "lvl": "%(levelname)s", "name": "%(name)s", %(message)s}'
        )
        handler.setFormatter(formatter)
        handler._vtlogger_stdout = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

    logger.propagate = False
    FILTERS = logger.filters
    return logger  # type: ignore[return-value]


def getLog(name: str) -> VTLogger:
    """Get a child logger of the app's main logger."""
    logger = logging.getLogger(f"{LOGGER_NAME}.{name}")
    for f in FILTERS:
        if f not in logger.filters:
            logger.addFilter(f)
    return logger  # type: ignore[return-value]
