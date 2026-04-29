"""Multi-Turn Reply Drafter — File 23.

Adapter protocol: ReplyDraftAdapter
Default: HeuristicReplyAdapter (fully deterministic, no LLM calls)

Module: MultiTurnDrafterModule  (run_type: reply_drafter)

For every thread where:
  - status = 'awaiting_reply'
  - last_direction = 'in'
  - no reply_draft message in the last RECENT_DRAFT_WINDOW_HOURS

The module:
  1. Builds a context window (last N messages + lead + ICP + signals + recent traces)
  2. Calls adapter.draft(context) → DraftResult
  3. Persists a new outreach_messages row (type='reply_draft')
  4. Persists a decision_traces row
  5. Adds a lead_thread_messages row (source='reply_draft')
  6. Updates thread: status='open', last_direction='out'
"""
from __future__ import annotations

import datetime as _dt
from typing import Protocol, runtime_checkable

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from vtutils.misc import now_iso

RECENT_DRAFT_WINDOW_HOURS = 2
CONTEXT_WINDOW_MESSAGES = 10


# ---------------------------------------------------------------------------
# Adapter Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ReplyDraftAdapter(Protocol):
    """Pluggable LLM / rule-based reply drafter."""

    def draft(self, context: dict) -> "DraftResult":
        ...


class DraftResult:
    __slots__ = ("subject", "body_text", "body_html", "rationale", "model_name",
                 "tokens_in", "tokens_out", "confidence")

    def __init__(
        self,
        *,
        subject: str,
        body_text: str,
        body_html: str = "",
        rationale: str = "",
        model_name: str = "heuristic",
        tokens_in: int = 0,
        tokens_out: int = 0,
        confidence: float = 0.8,
    ) -> None:
        self.subject = subject
        self.body_text = body_text
        self.body_html = body_html or body_text
        self.rationale = rationale
        self.model_name = model_name
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.confidence = confidence


class HeuristicReplyAdapter:
    """Deterministic template-based adapter — no LLM, always same output."""

    def draft(self, context: dict) -> DraftResult:
        thread = context.get("thread", {})
        icp = context.get("icp") or {}
        lead = context.get("lead") or {}
        messages = context.get("messages", [])
        signals = context.get("signals", [])

        last_in = next(
            (m for m in reversed(messages) if m.get("direction") == "in"),
            None,
        )
        contact_reply_body = (last_in or {}).get("body_text", "") or ""

        # Deterministic fields based on context
        value_prop = icp.get("value_proposition") or "our solution"
        angle = icp.get("outreach_angle") or "follow-up"
        subject = thread.get("subject") or "Re: Following up"
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        signal_mention = ""
        if signals:
            s = signals[0]
            signal_mention = (
                f" I noticed {s.get('signal_name', 'a buying signal')} "
                f"which made me think of {value_prop}."
            )

        rationale_parts = [
            f"angle={angle!r}",
            f"signals={len(signals)}",
            f"last_reply_length={len(contact_reply_body)}",
        ]

        body = (
            f"Thanks for getting back to me.\n\n"
            f"Based on your message, I believe {value_prop} could be a strong fit.{signal_mention}\n\n"
            f"Would you be open to a quick 15-minute call to explore further?\n\n"
            f"Best,\nOutreach Team"
        )

        rationale = (
            f"Heuristic reply. Context: {', '.join(rationale_parts)}. "
            f"Referenced value_prop={value_prop!r}."
        )

        return DraftResult(
            subject=subject,
            body_text=body,
            rationale=rationale,
            tokens_in=len(body) // 4,
            tokens_out=len(body) // 4,
            confidence=0.75,
        )


# ---------------------------------------------------------------------------
# Module-level pluggable singleton
# ---------------------------------------------------------------------------
_default_adapter: ReplyDraftAdapter = HeuristicReplyAdapter()


def get_default_reply_drafter() -> ReplyDraftAdapter:
    return _default_adapter


def set_default_reply_drafter(adapter: ReplyDraftAdapter) -> None:
    global _default_adapter
    _default_adapter = adapter


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------

class MultiTurnDrafterModule(BaseModule):
    name = "MultiTurnDrafterModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        limit = int(cfg.get("limit") or 100)
        adapter = get_default_reply_drafter()

        if not ctx.project_id:
            return ModuleResult.fail("project_id required for reply_drafter")

        recent_cutoff = (
            _dt.datetime.utcnow() - _dt.timedelta(hours=RECENT_DRAFT_WINDOW_HOURS)
        ).strftime("%Y-%m-%dT%H:%M:%S")

        threads = ctx.repos.lead_threads.find_awaiting_reply(
            int(ctx.project_id), limit=limit
        )

        drafted = 0
        skipped = 0

        for thread in threads:
            thread_id = int(thread["id"])
            # Skip if already drafted recently
            if ctx.repos.lead_thread_messages.has_recent_draft(
                thread_id, since_iso=recent_cutoff
            ):
                skipped += 1
                continue

            draft_result = _draft_for_thread(ctx, thread, adapter)
            if draft_result:
                drafted += 1

        log.info("reply_drafter_done", drafted=drafted, skipped=skipped)
        return ModuleResult.ok(
            input_count=len(threads),
            output_count=drafted,
            message=f"drafted={drafted} skipped={skipped}",
            data={"drafted": drafted, "skipped": skipped},
        )


def _draft_for_thread(ctx: PipelineContext, thread: dict, adapter: ReplyDraftAdapter) -> bool:
    """Build context, call adapter, persist draft + trace + message. Returns True on success."""
    thread_id = int(thread["id"])
    lead_id = thread.get("lead_id")
    contact_id = thread.get("contact_id")
    icp_id = thread.get("icp_id")

    messages = ctx.repos.lead_thread_messages.list_for_thread(
        thread_id, limit=CONTEXT_WINDOW_MESSAGES
    )
    lead = ctx.repos.lead_candidates.get(lead_id) if lead_id else None
    icp = ctx.repos.icps.get(icp_id) if icp_id else None
    signals: list[dict] = []
    if lead and lead.get("company_id"):
        signals = ctx.repos.signals.find_by_company(int(lead["company_id"]), limit=5)
    recent_traces = ctx.repos.decision_traces.list_for_lead(lead_id, limit=5) if lead_id else []

    context = {
        "thread": thread,
        "messages": messages,
        "lead": lead,
        "icp": icp,
        "signals": signals,
        "decision_traces": recent_traces,
    }

    try:
        result = adapter.draft(context)
    except Exception as exc:
        return False

    ts = now_iso()

    # 1) Persist outreach_message (type=reply_draft)
    msg_id = ctx.repos.outreach_messages.create({
        "project_id": int(ctx.project_id),
        "lead_id": lead_id,
        "channel": "email",
        "message_type": "reply_draft",
        "subject": result.subject,
        "body": result.body_text,
        "status": "draft",
        "generated_at": ts,
    })

    # 2) Persist decision_trace
    trace_id = ctx.repos.decision_traces.create({
        "pipeline_run_id": ctx.run_id if hasattr(ctx, "run_id") else None,
        "step_index": None,
        "module_name": MultiTurnDrafterModule.name,
        "lead_id": lead_id,
        "contact_id": contact_id,
        "decision_type": "draft",
        "input_snapshot": {
            "thread_id": thread_id,
            "message_count": len(messages),
            "signal_count": len(signals),
        },
        "rationale": result.rationale,
        "model_name": result.model_name,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "confidence": result.confidence,
    })

    # 3) Add thread message
    sent_at = ts
    ctx.repos.lead_thread_messages.create({
        "thread_id": thread_id,
        "direction": "out",
        "source": "reply_draft",
        "draft_id": msg_id,
        "subject": result.subject,
        "body_text": result.body_text,
        "body_html": result.body_html,
        "sent_at": sent_at,
        "decision_trace_id": trace_id,
    })

    # 4) Update thread
    ctx.repos.lead_threads.touch(thread_id, last_direction="out", last_message_at=sent_at)
    ctx.repos.lead_threads.update(thread_id, {"status": "open"})

    return True
