"""Quality control service (File 14).

Selects outreach_messages, runs the configured QualityChecker, persists rows
into quality_checks. Returns JSON-friendly summaries.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from services.outreach_generator import OUTREACH_STATUSES
from services.quality_checker import (
    QualityChecker, QualityResult, get_default_quality_checker,
)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _select_message_ids(
    repos, *,
    project_id: Optional[int],
    message_ids: Optional[list[int]],
    only_missing: bool,
    only_status: tuple[str, ...],
    limit: int,
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
    if only_missing:
        where.append(
            "om.id NOT IN (SELECT outreach_message_id FROM quality_checks "
            "WHERE outreach_message_id IS NOT NULL)"
        )
    sql = (
        "SELECT om.id AS id FROM outreach_messages om "
        "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY om.generated_at DESC, om.id DESC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.outreach_messages.storage.fetchall(sql, tuple(params))
    return [int(r["id"]) for r in rows]


# ---------------------------------------------------------------------------
# Per-message check
# ---------------------------------------------------------------------------

def quality_check_for_message(
    repos, message_id: int, *,
    checker: Optional[QualityChecker] = None,
    dry_run: bool = False,
) -> dict:
    msg = repos.outreach_messages.get(int(message_id))
    if not msg:
        return {"message_id": int(message_id), "ok": False, "error": "message_not_found"}

    contact: Optional[dict] = None
    lead = repos.lead_candidates.get(int(msg["lead_id"])) if msg.get("lead_id") else None
    if lead and lead.get("contact_id"):
        contact = repos.contacts.get(int(lead["contact_id"]))

    c = checker or get_default_quality_checker()
    result: QualityResult = c.check(message=msg, contact=contact, repos=repos)

    row = {
        "outreach_message_id": int(message_id),
        "checker": result.checker,
        "score": float(result.score),
        "passed": 1 if result.passed else 0,
        "rule_results": result.rule_results,
        "created_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
    }
    check_id: Optional[int] = None
    if not dry_run:
        check_id = repos.quality_checks.create(row)

    return {
        "message_id": int(message_id),
        "ok": True,
        "check_id": check_id,
        "checker": result.checker,
        "score": float(result.score),
        "passed": bool(result.passed),
        "rule_results": result.rule_results,
        "created_at": row["created_at"],
        "persisted": not dry_run,
    }


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def run_quality_batch(
    repos, *,
    project_id: Optional[int] = None,
    message_ids: Optional[list[int]] = None,
    only_missing: bool = True,
    only_status: tuple[str, ...] = ("draft",),
    limit: int = 200,
    dry_run: bool = False,
    checker: Optional[QualityChecker] = None,
) -> dict:
    # Validate only_status against taxonomy.
    norm_status: tuple[str, ...] = tuple(
        s for s in only_status if s in OUTREACH_STATUSES
    )
    ids = _select_message_ids(
        repos,
        project_id=project_id, message_ids=message_ids,
        only_missing=only_missing, only_status=norm_status, limit=limit,
    )
    c = checker or get_default_quality_checker()
    items: list[dict] = []
    persisted = 0
    failed = 0
    passed_count = 0
    failed_count = 0
    for mid in ids:
        res = quality_check_for_message(repos, mid, checker=c, dry_run=dry_run)
        if not res.get("ok"):
            failed += 1
            continue
        items.append({
            "message_id": res["message_id"],
            "check_id": res.get("check_id"),
            "score": res["score"],
            "passed": res["passed"],
        })
        if res.get("persisted"):
            persisted += 1
        if res["passed"]:
            passed_count += 1
        else:
            failed_count += 1
    return {
        "scanned": len(ids),
        "checked": len(items),
        "persisted": persisted,
        "failed": failed,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "only_status": list(norm_status),
        "only_missing": only_missing,
        "dry_run": dry_run,
        "message_ids": ids,
        "items": items,
    }
