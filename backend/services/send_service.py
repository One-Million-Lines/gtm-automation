"""Send service (File 15).

Selects approved outreach_messages, calls the EmailSender, persists
rows in outreach_sends and updates outreach_messages.status -> 'sent' on success.

Gates:
  - message_not_approved      (msg.status != 'approved')
  - daily_quota_exceeded      (count_sent_today(project) >= max_per_day)
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from services.email_sender import (
    EmailSender, SEND_STATUSES, get_default_email_sender,
)

DEFAULT_MAX_PER_DAY = 50


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _select_sendable_message_ids(
    repos, *,
    project_id: Optional[int],
    message_ids: Optional[list[int]],
    only_status: tuple[str, ...] = ("approved",),
    limit: int = 200,
    exclude_already_sent: bool = True,
) -> list[int]:
    if message_ids:
        return [int(x) for x in message_ids]
    where = ["1=1"]
    params: list[Any] = []
    if project_id is not None:
        where.append("lc.project_id = ?")
        params.append(int(project_id))
    if only_status:
        placeholders = ",".join(["?"] * len(only_status))
        where.append(f"om.status IN ({placeholders})")
        params.extend(only_status)
    if exclude_already_sent:
        where.append(
            "om.id NOT IN (SELECT outreach_message_id FROM outreach_sends "
            "WHERE status = 'sent')"
        )
    sql = (
        "SELECT om.id AS id FROM outreach_messages om "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY om.approved_at DESC, om.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.outreach_messages.storage.fetchall(sql, tuple(params))
    return [int(r["id"]) for r in rows]


# ---------------------------------------------------------------------------
# Per-message send
# ---------------------------------------------------------------------------

def send_for_message(
    repos, message_id: int, *,
    sender: Optional[EmailSender] = None,
    dry_run: bool = False,
    max_per_day: Optional[int] = None,
    enforce_quota: bool = True,
) -> dict:
    msg = repos.outreach_messages.get(int(message_id))
    if not msg:
        return {"message_id": int(message_id), "ok": False, "error": "message_not_found"}
    if (msg.get("status") or "").lower() != "approved":
        return {
            "message_id": int(message_id),
            "ok": False,
            "error": "message_not_approved",
            "current_status": msg.get("status"),
        }

    lead = repos.lead_candidates.get(int(msg["lead_id"])) if msg.get("lead_id") else None
    if not lead:
        return {"message_id": int(message_id), "ok": False, "error": "lead_not_found"}
    project_id = int(lead["project_id"])
    contact = repos.contacts.get(int(lead["contact_id"])) if lead.get("contact_id") else None
    to_addr = (contact or {}).get("email") or ""
    if not to_addr:
        return {"message_id": int(message_id), "ok": False, "error": "missing_recipient_email"}

    if enforce_quota and max_per_day is not None:
        sent_today = repos.outreach_sends.count_sent_today(project_id)
        if sent_today >= int(max_per_day):
            return {
                "message_id": int(message_id),
                "ok": False,
                "error": "daily_quota_exceeded",
                "sent_today": sent_today,
                "max_per_day": int(max_per_day),
            }

    s = sender or get_default_email_sender()
    if dry_run:
        return {
            "message_id": int(message_id),
            "ok": True,
            "dry_run": True,
            "to": to_addr,
            "provider": getattr(s, "name", "unknown"),
        }

    attempted_at = _now_iso()
    result = s.send(
        to=to_addr,
        subject=msg.get("subject") or "",
        body=msg.get("body") or "",
        body_html=msg.get("body_html"),
        outreach_message_id=int(message_id),
    )
    status = (result.get("status") or ("sent" if result.get("ok") else "failed")).lower()
    if status not in SEND_STATUSES:
        status = "failed"

    row = {
        "outreach_message_id": int(message_id),
        "provider": result.get("provider") or getattr(s, "name", "unknown"),
        "message_id_external": result.get("message_id_external"),
        "status": status,
        "attempted_at": attempted_at,
        "sent_at": attempted_at if status == "sent" else None,
        "error_message": result.get("error"),
        "raw_response": result.get("raw_response") or {},
    }
    send_id = repos.outreach_sends.create(row)

    if status == "sent":
        repos.outreach_messages.update(
            int(message_id),
            {"status": "sent", "sent_at": attempted_at},
        )

    return {
        "message_id": int(message_id),
        "ok": bool(result.get("ok")),
        "send_id": send_id,
        "provider": row["provider"],
        "message_id_external": row["message_id_external"],
        "status": status,
        "attempted_at": attempted_at,
        "sent_at": row["sent_at"],
        "error": result.get("error"),
        "to": to_addr,
    }


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def run_send_batch(
    repos, *,
    project_id: Optional[int] = None,
    message_ids: Optional[list[int]] = None,
    max_per_day: int = DEFAULT_MAX_PER_DAY,
    dry_run: bool = False,
    limit: int = 200,
    sender: Optional[EmailSender] = None,
) -> dict:
    sent_today = (
        repos.outreach_sends.count_sent_today(int(project_id))
        if project_id is not None else 0
    )
    remaining = max(0, int(max_per_day) - int(sent_today))

    ids = _select_sendable_message_ids(
        repos,
        project_id=project_id,
        message_ids=message_ids,
        only_status=("approved",),
        limit=limit,
        exclude_already_sent=True,
    )

    s = sender or get_default_email_sender()
    items: list[dict] = []
    sent = 0
    failed = 0
    skipped_quota = 0
    skipped_status = 0
    attempted = 0

    for mid in ids:
        if remaining <= 0 and not dry_run:
            skipped_quota += 1
            items.append({"message_id": mid, "ok": False, "error": "daily_quota_exceeded"})
            continue
        res = send_for_message(
            repos, mid,
            sender=s,
            dry_run=dry_run,
            max_per_day=None,  # quota tracked at batch level
            enforce_quota=False,
        )
        if res.get("error") == "message_not_approved":
            skipped_status += 1
            items.append(res)
            continue
        attempted += 1
        items.append(res)
        if res.get("ok"):
            if not dry_run:
                sent += 1
                remaining -= 1
            else:
                sent += 1
        else:
            failed += 1

    return {
        "scanned": len(ids),
        "attempted": attempted,
        "sent": sent,
        "failed": failed,
        "skipped_quota": skipped_quota,
        "skipped_status": skipped_status,
        "max_per_day": int(max_per_day),
        "sent_today": int(sent_today),
        "remaining": max(0, remaining),
        "dry_run": dry_run,
        "items": items,
    }
