"""Lead scoring service (File 12).

Orchestrates LeadScorer -> updates lead_candidates rows.
Pure-ish: takes a `repos`, optional `scorer`. Returns JSON-friendly summary.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from services.lead_scorer import (
    LeadScorer, ScoreResult, get_default_lead_scorer,
)


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

def _select_lead_ids(
    repos, *,
    project_id: Optional[int],
    icp_id: Optional[int],
    lead_ids: Optional[list[int]],
    only_missing: bool,
    limit: int,
) -> list[int]:
    if lead_ids:
        return [int(x) for x in lead_ids]
    where = ["1=1"]
    params: list[Any] = []
    if project_id is not None:
        where.append("project_id = ?")
        params.append(int(project_id))
    if icp_id is not None:
        where.append("icp_id = ?")
        params.append(int(icp_id))
    if only_missing:
        where.append("(scored_at IS NULL OR scored_at = '')")
    sql = (
        f"SELECT id FROM lead_candidates WHERE {' AND '.join(where)} "
        f"ORDER BY id ASC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.lead_candidates.storage.fetchall(sql, tuple(params))
    return [int(r["id"]) for r in rows]


def _load_signals_for(repos, *, company_id: Optional[int],
                      contact_id: Optional[int], limit: int = 200) -> list[dict]:
    """Combine company-scoped and contact-scoped signals (de-duped by id)."""
    seen: dict[int, dict] = {}
    if company_id is not None:
        for s in repos.signals.find_by_company(int(company_id), limit=limit):
            seen[int(s["id"])] = s
    if contact_id is not None:
        rows = repos.signals.find(
            {"contact_id": int(contact_id)},
            order_by="created_at DESC, id DESC",
            limit=limit,
        )
        for s in rows:
            seen[int(s["id"])] = s
    return list(seen.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_lead_for(
    repos, lead_id: int, *,
    scorer: Optional[LeadScorer] = None,
    dry_run: bool = False,
) -> dict:
    lead = repos.lead_candidates.get(int(lead_id))
    if not lead:
        return {"lead_id": int(lead_id), "ok": False, "error": "lead_not_found"}

    icp = repos.icps.get(int(lead["icp_id"])) if lead.get("icp_id") else None
    if not icp:
        return {"lead_id": int(lead_id), "ok": False, "error": "icp_not_found"}

    company = repos.companies.get(int(lead["company_id"])) if lead.get("company_id") else None
    if not company:
        return {"lead_id": int(lead_id), "ok": False, "error": "company_not_found"}

    contact = None
    if lead.get("contact_id"):
        contact = repos.contacts.get(int(lead["contact_id"]))

    signals = _load_signals_for(
        repos,
        company_id=lead.get("company_id"),
        contact_id=lead.get("contact_id"),
    )

    s = scorer or get_default_lead_scorer()
    result: ScoreResult = s.score(icp=icp, company=company, contact=contact, signals=signals)
    row = result.to_row()

    persisted = False
    if not dry_run:
        # set_status writes lead_status + extras; keep existing status if set.
        status = lead.get("lead_status") or "scored"
        repos.lead_candidates.set_status(int(lead_id), status, **row)
        persisted = True

    return {
        "lead_id": int(lead_id),
        "ok": True,
        "fit_score": row["icp_fit_score"],
        "intent_score": row["signal_score"],
        "combined_score": row["final_score"],
        "priority_tier": row["priority_tier"],
        "scored_at": row["scored_at"],
        "scoring_explanation": row["scoring_explanation"],
        "persisted": persisted,
        "signal_count": len(signals),
    }


def run_scoring_batch(
    repos, *,
    project_id: Optional[int] = None,
    icp_id: Optional[int] = None,
    lead_ids: Optional[list[int]] = None,
    only_missing: bool = True,
    limit: int = 500,
    dry_run: bool = False,
    scorer: Optional[LeadScorer] = None,
) -> dict:
    ids = _select_lead_ids(
        repos,
        project_id=project_id, icp_id=icp_id,
        lead_ids=lead_ids, only_missing=only_missing, limit=limit,
    )
    s = scorer or get_default_lead_scorer()
    scored: list[dict] = []
    failed = 0
    persisted = 0
    tier_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for lid in ids:
        res = score_lead_for(repos, lid, scorer=s, dry_run=dry_run)
        if not res.get("ok"):
            failed += 1
            continue
        scored.append(res)
        if res.get("persisted"):
            persisted += 1
        t = res.get("priority_tier") or "D"
        tier_counts[t] = tier_counts.get(t, 0) + 1
    return {
        "scanned": len(ids),
        "scored": len(scored),
        "persisted": persisted,
        "failed": failed,
        "tier_counts": tier_counts,
        "lead_ids": ids,
        "dry_run": dry_run,
    }
