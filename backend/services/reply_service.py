"""Reply service (File 16).

Persists replies in `outreach_replies`, classifies intent, and auto-suppresses
recipients on negative/unsubscribe signals.

Match strategy for outreach_send:
  - in_reply_to == outreach_sends.message_id_external, OR
  - message_id_external == outreach_sends.message_id_external
  Then resolve outreach_message_id from the matched outreach_send.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from services.reply_classifier import (
    REPLY_INTENTS, ReplyClassifier, classify_reply, get_default_reply_classifier,
)
from services.reply_ingestor import (
    ReplyIngestor, fetch_replies, get_default_reply_ingestor,
)


AUTO_SUPPRESS_INTENTS = ("negative", "unsubscribe")


def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Match outreach_send for an inbound payload
# ---------------------------------------------------------------------------

def _match_send_for_reply(
    repos, *,
    in_reply_to: Optional[str],
    message_id_external: Optional[str],
) -> Optional[dict]:
    candidates = [c for c in (in_reply_to, message_id_external) if c]
    for c in candidates:
        row = repos.outreach_sends.find_one({"message_id_external": c})
        if row:
            return row
    return None


# ---------------------------------------------------------------------------
# Per-reply ingestion
# ---------------------------------------------------------------------------

def ingest_reply(
    repos,
    payload: dict,
    *,
    classifier: Optional[ReplyClassifier] = None,
    dry_run: bool = False,
) -> dict:
    body = payload.get("body") or ""
    subject = payload.get("subject") or ""
    from_email = (payload.get("from_email") or "").strip().lower() or None
    in_reply_to = payload.get("in_reply_to")
    message_id_external = payload.get("message_id_external")
    explicit_message_id = payload.get("outreach_message_id")
    explicit_send_id = payload.get("outreach_send_id")

    send_row = None
    if explicit_send_id:
        send_row = repos.outreach_sends.get(int(explicit_send_id))
    if not send_row:
        send_row = _match_send_for_reply(
            repos,
            in_reply_to=in_reply_to,
            message_id_external=message_id_external,
        )

    outreach_send_id = int(send_row["id"]) if send_row else None
    outreach_message_id = (
        int(send_row["outreach_message_id"]) if send_row
        else (int(explicit_message_id) if explicit_message_id else None)
    )

    if outreach_message_id is None:
        return {
            "ok": False,
            "error": "no_matching_message",
            "in_reply_to": in_reply_to,
            "message_id_external": message_id_external,
        }

    cls_result = classify_reply(
        body=body, subject=subject, from_email=from_email,
        classifier=classifier or get_default_reply_classifier(),
    )
    intent = cls_result.get("intent") or "neutral"
    if intent not in REPLY_INTENTS:
        intent = "neutral"

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "outreach_message_id": outreach_message_id,
            "outreach_send_id": outreach_send_id,
            "intent": intent,
            "confidence": cls_result.get("confidence"),
            "from_email": from_email,
        }

    row = {
        "outreach_message_id": outreach_message_id,
        "outreach_send_id": outreach_send_id,
        "provider": payload.get("provider"),
        "message_id_external": message_id_external,
        "in_reply_to": in_reply_to,
        "from_email": from_email,
        "from_name": payload.get("from_name"),
        "subject": subject,
        "body": body,
        "body_html": payload.get("body_html"),
        "intent": intent,
        "confidence": cls_result.get("confidence"),
        "classifier": cls_result.get("classifier"),
        "raw_response": payload.get("raw_response") or {},
        "received_at": payload.get("received_at") or _now_iso(),
    }
    reply_id = repos.outreach_replies.create(row)

    suppressed = False
    if intent in AUTO_SUPPRESS_INTENTS and from_email:
        repos.suppression.add(
            "email", from_email,
            reason=f"reply_{intent}",
            source="reply_tracking",
        )
        suppressed = True
        # Best-effort: mark the originating send as 'replied'
        if send_row and (send_row.get("status") or "") in ("sent", "opened"):
            repos.outreach_sends.update(int(send_row["id"]), {"status": "replied"})

    return {
        "ok": True,
        "reply_id": int(reply_id),
        "outreach_message_id": outreach_message_id,
        "outreach_send_id": outreach_send_id,
        "intent": intent,
        "confidence": cls_result.get("confidence"),
        "classifier": cls_result.get("classifier"),
        "suppressed": suppressed,
        "from_email": from_email,
    }


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def run_reply_poll(
    repos, *,
    project_id: Optional[int] = None,
    ingestor: Optional[ReplyIngestor] = None,
    classifier: Optional[ReplyClassifier] = None,
    limit: int = 200,
    dry_run: bool = False,
) -> dict:
    payloads = fetch_replies(limit=limit, ingestor=ingestor or get_default_reply_ingestor())

    by_intent: dict[str, int] = {k: 0 for k in REPLY_INTENTS}
    items: list[dict] = []
    ingested = 0
    suppressed = 0
    for p in payloads:
        res = ingest_reply(repos, p, classifier=classifier, dry_run=dry_run)
        items.append(res)
        if res.get("ok"):
            ingested += 1
            intent = res.get("intent") or "neutral"
            by_intent[intent] = by_intent.get(intent, 0) + 1
            if res.get("suppressed"):
                suppressed += 1

    return {
        "scanned": len(payloads),
        "ingested": ingested,
        "suppressed": suppressed,
        "by_intent": by_intent,
        "dry_run": dry_run,
        "project_id": project_id,
        "items": items,
    }
