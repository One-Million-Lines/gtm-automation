"""Conversation service — File 23.

Provides:
  rebuild_threads          — group outreach_sends + outreach_replies into threads (idempotent)
  list_threads_for_project — paginated thread list
  get_thread_detail        — thread + merged message timeline
  mark_status              — change thread status
  add_manual_message       — inject a manual outbound message into a thread
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vtutils.misc import now_iso

if TYPE_CHECKING:
    from repositories.registry import RepoRegistry


# ---------------------------------------------------------------------------
# reconcile / rebuild
# ---------------------------------------------------------------------------

def rebuild_threads(repos: "RepoRegistry", *, project_id: int) -> dict:
    """Idempotently reconcile outreach_sends + outreach_replies into lead_threads.

    Strategy:
      - Group outreach_sends by contact_id within project.
      - The oldest send seeds the thread (subject comes from the outreach_message).
      - All replies on the same message chain are folded into the thread.
      - Already-reconciled sends/replies (send_id / reply_id already in
        lead_thread_messages) are skipped.

    Returns dict with created/updated/skipped counts.
    """
    already_send_ids: set[int] = {
        int(r["send_id"])
        for r in repos.storage.fetchall(
            "SELECT send_id FROM lead_thread_messages WHERE send_id IS NOT NULL"
        )
    }
    already_reply_ids: set[int] = {
        int(r["reply_id"])
        for r in repos.storage.fetchall(
            "SELECT reply_id FROM lead_thread_messages WHERE reply_id IS NOT NULL"
        )
    }

    # All sends for this project, ordered oldest-first
    sends = repos.storage.fetchall(
        "SELECT os.*, om.lead_id, om.subject, "
        "lc.project_id, lc.contact_id, lc.icp_id "
        "FROM outreach_sends os "
        "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        "WHERE lc.project_id = ? "
        "ORDER BY os.attempted_at ASC, os.id ASC",
        (int(project_id),),
    )

    created = updated = skipped = 0

    for s in sends:
        send_id = int(s["id"])
        contact_id = s["contact_id"]
        lead_id = s["lead_id"]
        icp_id = s["icp_id"]
        subject = s.get("subject") or ""
        attempted_at = s.get("attempted_at") or s.get("sent_at") or now_iso()

        if send_id in already_send_ids:
            skipped += 1
            continue

        # Find or create thread for this contact
        thread = repos.lead_threads.get_by_contact(project_id, contact_id) if contact_id else None
        if thread is None:
            thread_id = repos.lead_threads.create({
                "project_id": int(project_id),
                "icp_id": icp_id,
                "lead_id": lead_id,
                "contact_id": contact_id,
                "subject": subject,
                "status": "awaiting_reply",
                "last_message_at": attempted_at,
                "last_direction": "out",
                "message_count": 0,
            })
            created += 1
        else:
            thread_id = int(thread["id"])
            updated += 1

        # Add the send as a thread message
        repos.lead_thread_messages.create({
            "thread_id": thread_id,
            "direction": "out",
            "source": "outreach_send",
            "send_id": send_id,
            "subject": subject,
            "body_text": None,
            "sent_at": attempted_at,
        })
        repos.lead_threads.touch(thread_id, last_direction="out", last_message_at=attempted_at)

    # Now fold in replies
    replies = repos.storage.fetchall(
        "SELECT orep.*, om.lead_id, lc.project_id, lc.contact_id "
        "FROM outreach_replies orep "
        "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        "WHERE lc.project_id = ? "
        "ORDER BY orep.received_at ASC, orep.id ASC",
        (int(project_id),),
    )

    for r in replies:
        reply_id = int(r["id"])
        contact_id = r["contact_id"]
        received_at = r.get("received_at") or now_iso()

        if reply_id in already_reply_ids:
            continue

        thread = repos.lead_threads.get_by_contact(project_id, contact_id) if contact_id else None
        if thread is None:
            continue

        thread_id = int(thread["id"])
        repos.lead_thread_messages.create({
            "thread_id": thread_id,
            "direction": "in",
            "source": "outreach_reply",
            "reply_id": reply_id,
            "subject": r.get("subject"),
            "body_text": r.get("body"),
            "received_at": received_at,
        })
        repos.lead_threads.touch(thread_id, last_direction="in", last_message_at=received_at)
        repos.lead_threads.update(thread_id, {"status": "awaiting_reply"})

    return {"created": created, "updated": updated, "skipped": skipped}


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def list_threads_for_project(
    repos: "RepoRegistry",
    project_id: int,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    threads = repos.lead_threads.find_for_project(
        project_id, status=status, limit=limit
    )
    return threads


def get_thread_detail(repos: "RepoRegistry", thread_id: int) -> dict | None:
    thread = repos.lead_threads.get(thread_id)
    if thread is None:
        return None
    messages = repos.lead_thread_messages.list_for_thread(thread_id)
    # Enrich each message with its decision trace if present
    for msg in messages:
        dtid = msg.get("decision_trace_id")
        if dtid:
            msg["decision_trace"] = repos.decision_traces.get(int(dtid))
        else:
            msg["decision_trace"] = None
    thread["messages"] = messages
    return thread


def mark_status(repos: "RepoRegistry", thread_id: int, status: str) -> dict:
    valid = {"open", "awaiting_reply", "replied", "closed", "bounced"}
    if status not in valid:
        raise ValueError(f"Invalid status {status!r}; must be one of {sorted(valid)}")
    repos.lead_threads.update(thread_id, {"status": status})
    row = repos.lead_threads.get(thread_id)
    if row is None:
        raise ValueError(f"Thread {thread_id} not found")
    return row


def add_manual_message(
    repos: "RepoRegistry",
    thread_id: int,
    *,
    direction: str = "out",
    subject: str | None = None,
    body_text: str | None = None,
    body_html: str | None = None,
) -> dict:
    valid_dirs = {"out", "in"}
    if direction not in valid_dirs:
        raise ValueError(f"direction must be 'out' or 'in', got {direction!r}")
    thread = repos.lead_threads.get(thread_id)
    if thread is None:
        raise ValueError(f"Thread {thread_id} not found")
    ts = now_iso()
    msg_id = repos.lead_thread_messages.create({
        "thread_id": thread_id,
        "direction": direction,
        "source": "manual",
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "sent_at": ts if direction == "out" else None,
        "received_at": ts if direction == "in" else None,
    })
    repos.lead_threads.touch(thread_id, last_direction=direction, last_message_at=ts)
    if direction == "out":
        repos.lead_threads.update(thread_id, {"status": "awaiting_reply"})
    elif direction == "in":
        repos.lead_threads.update(thread_id, {"status": "awaiting_reply"})
    return repos.lead_thread_messages.get(msg_id) or {}
