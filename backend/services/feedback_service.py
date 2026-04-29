"""Feedback ingestion + lifecycle loop service — File 20.

- record_feedback: write a feedback_event (and optionally a lifecycle transition).
- transition_lead: validated state machine over lead_candidates.lifecycle_stage.
- apply_unapplied_feedback: scan unapplied events, materialize side-effects.
- ingest_reply_feedback / ingest_export_feedback: auto-bridges from File 16/19.
- Pluggable LifecycleSyncAdapter for CRM webhook stub.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from repositories import RepoRegistry
from vtutils.misc import now_iso
from vtutils.vtlogger import getLog

vtlog = getLog("services.feedback")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LIFECYCLE_STAGES = (
    "new",
    "contacted",
    "engaged",
    "qualified",
    "meeting_booked",
    "won",
    "lost",
    "unsubscribed",
    "disqualified",
)

ALLOWED_KINDS = (
    "thumbs_up", "thumbs_down",
    "lead_qualified", "lead_disqualified",
    "meeting_booked", "won", "lost",
    "unsubscribe", "note",
)

ALLOWED_SOURCES = ("human", "reply", "crm_sync", "export_delivered", "system")

# from_stage -> set of allowed to_stages.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new":            {"contacted", "engaged", "qualified", "disqualified", "unsubscribed"},
    "contacted":      {"engaged", "qualified", "disqualified", "unsubscribed", "lost"},
    "engaged":        {"qualified", "meeting_booked", "disqualified", "unsubscribed", "lost"},
    "qualified":      {"meeting_booked", "won", "lost", "disqualified", "unsubscribed"},
    "meeting_booked": {"won", "lost", "disqualified", "unsubscribed"},
    "won":            set(),
    "lost":           set(),
    "unsubscribed":   set(),
    "disqualified":   set(),
}

# Maps feedback kinds to a target lifecycle_stage when the kind alone is decisive.
KIND_TO_STAGE: dict[str, str] = {
    "lead_qualified":    "qualified",
    "lead_disqualified": "disqualified",
    "meeting_booked":    "meeting_booked",
    "won":               "won",
    "lost":              "lost",
    "unsubscribe":       "unsubscribed",
}


# ---------------------------------------------------------------------------
# Pluggable lifecycle sync adapter (CRM webhook stub)
# ---------------------------------------------------------------------------
class LifecycleSyncAdapter(Protocol):
    name: str

    def sync_transition(self, transition: dict, lead: dict) -> dict: ...


class FakeLifecycleSyncAdapter:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def sync_transition(self, transition: dict, lead: dict) -> dict:
        record = {
            "transition_id": transition.get("id"),
            "lead_id": transition.get("lead_id"),
            "to_status": transition.get("to_status"),
            "synced_at": now_iso(),
        }
        self.calls.append(record)
        vtlog.info(
            "lifecycle_sync_fake",
            lead_id=transition.get("lead_id"),
            to_status=transition.get("to_status"),
        )
        return {"synced": True, "simulated": True, "adapter": self.name, **record}


_default_lifecycle_sync_adapter: LifecycleSyncAdapter = FakeLifecycleSyncAdapter()


def get_default_lifecycle_sync_adapter() -> LifecycleSyncAdapter:
    return _default_lifecycle_sync_adapter


def set_default_lifecycle_sync_adapter(adapter: Optional[LifecycleSyncAdapter]) -> None:
    """Override (or reset to default with adapter=None) the lifecycle sync adapter."""
    global _default_lifecycle_sync_adapter
    if adapter is None:
        _default_lifecycle_sync_adapter = FakeLifecycleSyncAdapter()
    else:
        _default_lifecycle_sync_adapter = adapter


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------
def _current_stage(lead: dict) -> str:
    return (lead.get("lifecycle_stage") or "new").strip().lower()


def transition_lead(
    repos: RepoRegistry,
    *,
    lead_id: int,
    to_status: str,
    reason: str | None = None,
    source: str = "system",
    feedback_event_id: int | None = None,
    adapter: Optional[LifecycleSyncAdapter] = None,
) -> dict:
    if to_status not in LIFECYCLE_STAGES:
        raise ValueError(f"unknown lifecycle stage: {to_status}")
    lead = repos.lead_candidates.get(int(lead_id))
    if not lead:
        raise ValueError(f"lead {lead_id} not found")
    from_status = _current_stage(lead)
    if from_status == to_status:
        return {"lead_id": lead_id, "from_status": from_status, "to_status": to_status,
                "noop": True}
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise ValueError(
            f"illegal transition {from_status!r} -> {to_status!r}; "
            f"allowed from {from_status!r}: {sorted(allowed)}"
        )
    repos.lead_candidates.update(int(lead_id), {"lifecycle_stage": to_status})
    tid = repos.lifecycle_transitions.create({
        "lead_id": int(lead_id),
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
        "source": source,
        "feedback_event_id": feedback_event_id,
    })
    transition = repos.lifecycle_transitions.get(tid) or {
        "id": tid, "lead_id": lead_id, "from_status": from_status, "to_status": to_status,
    }
    sync_adapter = adapter or get_default_lifecycle_sync_adapter()
    try:
        sync_result = sync_adapter.sync_transition(transition, lead)
    except Exception as exc:
        vtlog.error("lifecycle_sync_failed", error=str(exc), lead_id=lead_id)
        sync_result = {"synced": False, "error": str(exc)}
    return {
        "transition": transition,
        "from_status": from_status,
        "to_status": to_status,
        "lead_id": int(lead_id),
        "sync": sync_result,
    }


def record_feedback(
    repos: RepoRegistry,
    *,
    project_id: int,
    kind: str,
    source: str = "human",
    lead_id: int | None = None,
    icp_id: int | None = None,
    outreach_message_id: int | None = None,
    variant_id: int | None = None,
    payload: dict | None = None,
    weight: float = 1.0,
    auto_apply: bool = False,
) -> dict:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unknown feedback kind: {kind}")
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"unknown feedback source: {source}")
    if not repos.projects.get(int(project_id)):
        raise ValueError(f"project {project_id} not found")
    if lead_id is not None and not repos.lead_candidates.get(int(lead_id)):
        raise ValueError(f"lead {lead_id} not found")

    eid = repos.feedback_events.create({
        "project_id": int(project_id),
        "icp_id": int(icp_id) if icp_id is not None else None,
        "lead_id": int(lead_id) if lead_id is not None else None,
        "outreach_message_id": int(outreach_message_id) if outreach_message_id is not None else None,
        "variant_id": int(variant_id) if variant_id is not None else None,
        "source": source,
        "kind": kind,
        "payload": payload or {},
        "weight": float(weight),
        "applied": 0,
    })
    event = repos.feedback_events.get(eid)
    transition_result: dict | None = None
    if auto_apply:
        try:
            transition_result = _apply_one_event(repos, event)
            repos.feedback_events.mark_applied(eid)
        except ValueError as exc:
            vtlog.warning("feedback_auto_apply_failed", event_id=eid, error=str(exc))
    return {"event": event, "transition": transition_result}


def _apply_one_event(repos: RepoRegistry, event: dict) -> dict | None:
    """Materialize side-effects for a single event. Returns transition dict or None."""
    kind = event.get("kind")
    lead_id = event.get("lead_id")
    if not lead_id:
        return None
    target_stage = KIND_TO_STAGE.get(kind or "")
    if not target_stage:
        return None
    lead = repos.lead_candidates.get(int(lead_id))
    if not lead:
        return None
    if _current_stage(lead) == target_stage:
        return None
    allowed = ALLOWED_TRANSITIONS.get(_current_stage(lead), set())
    if target_stage not in allowed:
        # Skip silently if illegal — caller can inspect events' applied=1 anyway.
        return None
    return transition_lead(
        repos,
        lead_id=int(lead_id),
        to_status=target_stage,
        reason=f"feedback_event:{event.get('id')}:{kind}",
        source=event.get("source") or "system",
        feedback_event_id=int(event["id"]),
    )


def apply_unapplied_feedback(
    repos: RepoRegistry,
    *,
    project_id: int,
    limit: int = 200,
) -> dict:
    events = repos.feedback_events.list_unapplied(int(project_id), limit=limit)
    applied = 0
    transitions: list[dict] = []
    errors: list[dict] = []
    for ev in events:
        try:
            t = _apply_one_event(repos, ev)
            repos.feedback_events.mark_applied(int(ev["id"]))
            applied += 1
            if t:
                transitions.append(t)
        except Exception as exc:
            errors.append({"event_id": ev.get("id"), "error": str(exc)})
    return {"applied": applied, "transitions": transitions, "errors": errors,
            "scanned": len(events)}


def feedback_summary(repos: RepoRegistry, project_id: int) -> dict:
    by_kind = repos.feedback_events.count_by_kind(int(project_id))
    # by_stage: count lead_candidates grouped by lifecycle_stage in this project.
    sql = (
        "SELECT lifecycle_stage AS stage, COUNT(*) AS n "
        "FROM lead_candidates WHERE project_id = ? GROUP BY lifecycle_stage"
    )
    rows = repos.storage.fetchall(sql, (int(project_id),))
    by_stage = {(r["stage"] or "new"): int(r["n"]) for r in rows}
    recent = repos.feedback_events.list_for_project(int(project_id), limit=20)
    return {"by_kind": by_kind, "by_stage": by_stage, "recent": recent}


# ---------------------------------------------------------------------------
# Auto-bridges
# ---------------------------------------------------------------------------
_REPLY_INTENT_TO_KIND: dict[str, str] = {
    "positive":     "meeting_booked",
    "interested":   "meeting_booked",
    "unsubscribe":  "unsubscribe",
    "negative":     "lead_disqualified",
    "not_interested": "lead_disqualified",
}


def _project_id_for_message(repos: RepoRegistry, message_id: int) -> int | None:
    msg = repos.outreach_messages.get(int(message_id))
    if not msg:
        return None
    pid = msg.get("project_id")
    if pid:
        return int(pid)
    lead_id = msg.get("lead_id")
    if not lead_id:
        return None
    lead = repos.lead_candidates.get(int(lead_id))
    return int(lead["project_id"]) if lead else None


def ingest_reply_feedback(repos: RepoRegistry, reply: dict) -> Optional[dict]:
    """Translate an outreach_replies row into a feedback_event (auto-applied)."""
    if not reply:
        return None
    intent = (reply.get("intent") or "").strip().lower()
    kind = _REPLY_INTENT_TO_KIND.get(intent)
    if not kind:
        return None
    msg_id = reply.get("outreach_message_id")
    if not msg_id:
        return None
    msg = repos.outreach_messages.get(int(msg_id))
    if not msg:
        return None
    lead_id = msg.get("lead_id")
    pid = _project_id_for_message(repos, int(msg_id))
    if not pid:
        return None
    return record_feedback(
        repos,
        project_id=int(pid),
        kind=kind,
        source="reply",
        lead_id=int(lead_id) if lead_id else None,
        outreach_message_id=int(msg_id),
        payload={
            "reply_id": reply.get("id"),
            "intent": intent,
            "from_email": reply.get("from_email"),
            "subject": reply.get("subject"),
        },
        weight=float(reply.get("confidence") or 0.5),
        auto_apply=True,
    )


def ingest_export_feedback(repos: RepoRegistry, export: dict, items: list[dict]) -> int:
    """For each delivered export item, drop a 'note' event + advance new/engaged → contacted."""
    if not export or (export.get("status") or "") != "delivered":
        return 0
    project_id = export.get("project_id")
    if not project_id:
        return 0
    count = 0
    for item in items or []:
        lead_id = item.get("lead_id")
        if not lead_id:
            continue
        lead = repos.lead_candidates.get(int(lead_id))
        if not lead:
            continue
        record_feedback(
            repos,
            project_id=int(project_id),
            kind="note",
            source="export_delivered",
            lead_id=int(lead_id),
            payload={"export_id": export.get("id"),
                     "destination": export.get("destination")},
            weight=0.5,
            auto_apply=False,
        )
        count += 1
        cur = _current_stage(lead)
        if cur in ("new", "engaged"):
            try:
                transition_lead(
                    repos,
                    lead_id=int(lead_id),
                    to_status="contacted" if cur == "new" else cur,
                    reason=f"export:{export.get('id')}",
                    source="export_delivered",
                )
            except ValueError:
                pass
    return count


# ---------------------------------------------------------------------------
# Pipeline-friendly aggregator (used by FeedbackIngestionModule)
# ---------------------------------------------------------------------------
def run_ingestion(
    repos: RepoRegistry,
    *,
    project_id: int,
    include_replies: bool = True,
    include_exports: bool = True,
    dry_run: bool = False,
) -> dict:
    if not repos.projects.get(int(project_id)):
        raise ValueError(f"project {project_id} not found")
    reply_events = 0
    export_events = 0

    if include_replies:
        # Walk recent unprocessed replies for the project (50 latest).
        replies = repos.outreach_replies.list_for_project(int(project_id), limit=50)
        for r in replies:
            # Skip if we already have a feedback_event for this reply (idempotent-ish).
            existing = repos.feedback_events.find(
                {"project_id": int(project_id), "source": "reply"},
                limit=200,
            )
            seen_reply_ids = {
                (e.get("payload") or {}).get("reply_id") for e in existing
            }
            if r.get("id") in seen_reply_ids:
                continue
            if dry_run:
                reply_events += 1
                continue
            ev = ingest_reply_feedback(repos, r)
            if ev:
                reply_events += 1

    if include_exports:
        delivered = repos.lead_exports.list_for_project(
            int(project_id), status="delivered", limit=20,
        )
        for exp in delivered:
            existing = repos.feedback_events.find(
                {"project_id": int(project_id), "source": "export_delivered"},
                limit=500,
            )
            already_seen = {
                (e.get("payload") or {}).get("export_id") for e in existing
            }
            if exp.get("id") in already_seen:
                continue
            items = repos.lead_export_items.list_for_export(int(exp["id"]), limit=2000)
            if dry_run:
                export_events += len(items)
                continue
            export_events += ingest_export_feedback(repos, exp, items)

    apply_result = (
        {"applied": 0, "transitions": [], "errors": [], "scanned": 0}
        if dry_run
        else apply_unapplied_feedback(repos, project_id=int(project_id))
    )
    return {
        "reply_events": reply_events,
        "export_events": export_events,
        "apply": apply_result,
    }
