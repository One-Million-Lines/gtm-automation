"""LLM factory — single GenerativeLLM instance backed by env vars.

Returns None when no API keys are configured; callers should degrade
gracefully (e.g. keep using HeuristicReplyAdapter).

Env vars:
  OPENAI_APIKEY
  ANTHROPIC_API_KEY
  GOOGLE_GENAI_APIKEY
  VERTEXAI_APIKEY
  GOOGLE_SA   (path to service account JSON)
"""
from __future__ import annotations

import os
from typing import Optional

from vtutils.vtlogger import getLog

_llm_instance = None
_initialized = False
_log = getLog("llm_factory")


def _has_any_key() -> bool:
    return any(
        os.environ.get(k)
        for k in ("OPENAI_APIKEY", "ANTHROPIC_API_KEY", "GOOGLE_GENAI_APIKEY", "VERTEXAI_APIKEY")
    )


def get_llm():
    """Return a singleton GenerativeLLM, or None if not configured."""
    global _llm_instance, _initialized
    if _initialized:
        return _llm_instance
    _initialized = True

    if not _has_any_key():
        _log.info("llm_no_keys_configured")
        return None
    try:
        from vtlib.generative_llm import GenerativeLLM
        _llm_instance = GenerativeLLM({
            "OPENAI_APIKEY": os.environ.get("OPENAI_APIKEY", ""),
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
            "GOOGLE_GENAI_APIKEY": os.environ.get("GOOGLE_GENAI_APIKEY", ""),
            "VERTEXAI_APIKEY": os.environ.get("VERTEXAI_APIKEY", ""),
            "GOOGLE_SA": None,
        })
        _log.info("llm_initialized", model=_llm_instance.DEFAULT_MODEL)
    except Exception as exc:
        _log.error("llm_init_failed", exc=str(exc))
        _llm_instance = None
    return _llm_instance


def reset_llm() -> None:
    """For tests."""
    global _llm_instance, _initialized
    _llm_instance = None
    _initialized = False
