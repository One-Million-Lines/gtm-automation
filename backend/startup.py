"""Startup wiring — install LLM + email defaults based on env.

Called from main.py at app startup. Idempotent.
"""
from __future__ import annotations

import os

from api_shared import vtlog


def install_defaults() -> dict:
    """Wire default reply drafter + email sender from env. Returns summary."""
    summary: dict = {}

    # ── Reply drafter ────────────────────────────────────────────────────────
    try:
        from services.llm_factory import get_llm
        llm = get_llm()
        if llm is not None and os.environ.get("USE_LLM_DRAFTER", "true").lower() in ("1", "true", "yes"):
            from pipeline.modules.llm_reply_adapter import LLMReplyAdapter
            from pipeline.modules.multi_turn_drafter_module import set_default_reply_drafter
            adapter = LLMReplyAdapter(llm)
            set_default_reply_drafter(adapter)
            summary["reply_drafter"] = f"LLMReplyAdapter({adapter.model})"
        else:
            summary["reply_drafter"] = "HeuristicReplyAdapter (default)"
    except Exception as exc:
        vtlog.error("install_reply_drafter_failed", exc=str(exc))
        summary["reply_drafter"] = f"failed: {exc}"

    # ── Reply classifier (LLM-backed if available) ───────────────────────────
    try:
        from services.llm_factory import get_llm
        llm = get_llm()
        if llm is not None and os.environ.get("USE_LLM_CLASSIFIER", "true").lower() in ("1", "true", "yes"):
            from services.reply_classifier import LLMReplyClassifier, set_default_reply_classifier
            set_default_reply_classifier(LLMReplyClassifier(llm=llm))
            summary["reply_classifier"] = "LLMReplyClassifier"
        else:
            summary["reply_classifier"] = "RuleBasedReplyClassifier (default)"
    except Exception as exc:
        vtlog.error("install_reply_classifier_failed", exc=str(exc))
        summary["reply_classifier"] = f"failed: {exc}"

    # ── Email sender ─────────────────────────────────────────────────────────
    try:
        from services.email_sender import build_sender_from_env, set_default_email_sender
        sender = build_sender_from_env()
        set_default_email_sender(sender)
        summary["email_sender"] = sender.name
    except Exception as exc:
        vtlog.error("install_email_sender_failed", exc=str(exc))
        summary["email_sender"] = f"failed: {exc}"

    vtlog.info("startup_defaults_installed", **summary)
    return summary
