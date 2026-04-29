"""LLM-backed ReplyDraftAdapter using GenerativeLLM (litellm).

Drop-in replacement for HeuristicReplyAdapter. If the LLM call fails for
any reason, falls back to the heuristic adapter so the pipeline keeps running.
"""
from __future__ import annotations

import json
import os
from typing import Any

from pipeline.modules.multi_turn_drafter_module import (
    DraftResult,
    HeuristicReplyAdapter,
)
from vtutils.vtlogger import getLog

_log = getLog("llm_reply_adapter")

DEFAULT_MODEL = os.environ.get("LLM_REPLY_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "You are an expert B2B sales rep. You write concise, friendly, "
    "non-pushy reply emails to inbound prospect responses. "
    "Always reference what the prospect said, propose a clear next step, "
    "and keep the body under 120 words. "
    "Respond ONLY in JSON with keys: subject, body_text, rationale, confidence (0-1)."
)


def _build_user_prompt(context: dict) -> str:
    thread = context.get("thread", {}) or {}
    icp = context.get("icp") or {}
    lead = context.get("lead") or {}
    contact = context.get("contact") or {}
    messages = context.get("messages", []) or []
    signals = context.get("signals", []) or []

    last_in = next(
        (m for m in reversed(messages) if m.get("direction") == "in"), None
    )
    last_out = next(
        (m for m in reversed(messages) if m.get("direction") == "out"), None
    )

    parts = [
        f"## Prospect",
        f"Name: {contact.get('first_name','')} {contact.get('last_name','')}".strip(),
        f"Title: {contact.get('job_title','')}",
        f"Company: {(context.get('company') or {}).get('name','')}",
        "",
        "## Our value proposition",
        icp.get("value_proposition") or "(none)",
        "",
        f"## Outreach angle: {icp.get('outreach_angle') or '(none)'}",
        "",
    ]
    if signals:
        parts.append("## Top buying signals")
        for s in signals[:3]:
            parts.append(
                f"- {s.get('signal_type','')}/{s.get('signal_name','')} "
                f"strength={s.get('strength_score','?')}"
            )
        parts.append("")

    if last_out:
        parts += [
            "## Our last message",
            f"Subject: {last_out.get('subject','')}",
            (last_out.get("body_text") or "")[:1200],
            "",
        ]
    if last_in:
        parts += [
            "## Their reply (most recent)",
            (last_in.get("body_text") or "")[:1500],
            "",
        ]

    parts.append(
        "## Task\n"
        "Write a reply email. Output JSON only: "
        '{"subject":"...","body_text":"...","rationale":"why this reply","confidence":0.0-1.0}'
    )
    return "\n".join(parts)


class LLMReplyAdapter:
    """Calls GenerativeLLM; falls back to heuristic on any error."""

    def __init__(self, llm: Any, *, model: str = DEFAULT_MODEL):
        self.llm = llm
        self.model = model
        self._fallback = HeuristicReplyAdapter()

    def draft(self, context: dict) -> DraftResult:
        if self.llm is None:
            return self._fallback.draft(context)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(context)},
        ]
        try:
            response, meta = self.llm.call(
                messages,
                llm_model=self.model,
                temperature=0.4,
                response_format="json",
            )
            data = response if isinstance(response, dict) else json.loads(response or "{}")
            subject = (data.get("subject") or "").strip()
            body_text = (data.get("body_text") or "").strip()
            if not subject or not body_text:
                raise ValueError("LLM returned empty subject/body")
            return DraftResult(
                subject=subject,
                body_text=body_text,
                body_html=body_text.replace("\n", "<br/>"),
                rationale=(data.get("rationale") or "")[:500],
                model_name=meta.get("model", self.model),
                tokens_in=int(meta.get("tokens", 0)) or 0,
                tokens_out=0,
                confidence=float(data.get("confidence", 0.7)),
            )
        except Exception as exc:
            _log.error("llm_draft_failed_falling_back", exc=str(exc))
            return self._fallback.draft(context)
