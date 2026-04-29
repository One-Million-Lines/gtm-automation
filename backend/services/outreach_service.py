"""Outreach generation service (File 13).

Orchestrates OutreachGenerator -> persists rows in outreach_messages.
Pure-ish: takes a `repos`, optional `generator`. Returns JSON-friendly summaries.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from services.outreach_generator import (
    OUTREACH_CHANNELS, OUTREACH_STATUSES, OutreachGenerator, OutreachResult,
    _matched_criteria, _top_signal_contributions, get_default_outreach_generator,
    tier_meets_min,
)
from services.experiment_service import (
    assign_lead_to_experiment, find_active_experiment_for_lead, render_variant,
)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _select_lead_ids(
    repos, *,
    project_id: Optional[int],
    icp_id: Optional[int],
    lead_ids: Optional[list[int]],
    min_tier: str,
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
    # tier gating: only A..min_tier
    allowed = [t for t, _ in (("A", 0), ("B", 1), ("C", 2), ("D", 3))
               if tier_meets_min(t, min_tier)]
    if allowed:
        placeholders = ",".join(["?"] * len(allowed))
        where.append(f"priority_tier IN ({placeholders})")
        params.extend(allowed)
    if only_missing:
        where.append(
            "id NOT IN (SELECT lead_id FROM outreach_messages WHERE lead_id IS NOT NULL)"
        )
    sql = (
        f"SELECT id FROM lead_candidates WHERE {' AND '.join(where)} "
        f"ORDER BY COALESCE(final_score, 0) DESC, id ASC LIMIT ?"
    )
    params.append(int(limit))
    rows = repos.lead_candidates.storage.fetchall(sql, tuple(params))
    return [int(r["id"]) for r in rows]


# ---------------------------------------------------------------------------
# Generate / persist
# ---------------------------------------------------------------------------

def _build_row_from_result(result: OutreachResult, *, lead_id: int, channel: str,
                           variant_id: Optional[int] = None) -> dict:
    return {
        "lead_id": int(lead_id),
        "channel": channel,
        "subject": result.subject,
        "body": result.body,
        "body_html": result.body_html,
        "status": "draft",
        "model": result.model,
        "prompt": result.prompt,
        "prompt_tokens": int(result.prompt_tokens or 0),
        "completion_tokens": int(result.completion_tokens or 0),
        "context": result.context or {},
        "raw_response": result.raw_response or {},
        "generated_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
        "variant_id": int(variant_id) if variant_id is not None else None,
    }


def generate_outreach_for(
    repos, lead_id: int, *,
    generator: Optional[OutreachGenerator] = None,
    channel: str = "email",
    dry_run: bool = False,
) -> dict:
    if channel not in OUTREACH_CHANNELS:
        return {"lead_id": int(lead_id), "ok": False, "error": f"unknown_channel:{channel}"}

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

    explanation = lead.get("scoring_explanation") if isinstance(
        lead.get("scoring_explanation"), dict
    ) else None
    signals_top = _top_signal_contributions(explanation, n=3)
    matched = _matched_criteria(explanation)

    # ---- variant assignment (File 18) ----
    variant_id: Optional[int] = None
    rendered: Optional[dict] = None
    try:
        active_exp = find_active_experiment_for_lead(repos, lead)
    except Exception:
        active_exp = None
    if active_exp:
        try:
            assignment = assign_lead_to_experiment(
                repos, int(lead_id), int(active_exp["id"]),
            )
            variant_id = int(assignment["variant_id"])
            variant = repos.outreach_variants.get(variant_id)
            if variant and (variant.get("subject_template") or variant.get("body_template")):
                contact_d = contact or {}
                tpl_ctx = {
                    "first_name": contact_d.get("first_name") or "there",
                    "last_name": contact_d.get("last_name") or "",
                    "full_name": contact_d.get("full_name") or "",
                    "job_title": contact_d.get("job_title") or "",
                    "email": contact_d.get("email") or "",
                    "company_name": company.get("name") or company.get("domain") or "",
                    "company_domain": company.get("domain") or "",
                    "industry": company.get("industry") or "",
                    "value_proposition": icp.get("value_proposition") or "",
                    "outreach_angle": icp.get("outreach_angle") or "",
                }
                rendered = render_variant(variant, tpl_ctx)
        except Exception:
            variant_id = None
            rendered = None

    if rendered and (rendered.get("subject") or rendered.get("body")):
        result = OutreachResult(
            subject=str(rendered.get("subject") or "Quick thought"),
            body=str(rendered.get("body") or ""),
            body_html=None,
            model="variant_template",
            prompt="",
            prompt_tokens=0,
            completion_tokens=0,
            context={
                "variant_id": variant_id,
                "cta": rendered.get("cta"),
                "channel": channel,
            },
            raw_response={"variant_id": variant_id},
        )
    else:
        g = generator or get_default_outreach_generator()
        result = g.generate(
            icp=icp, lead=lead, contact=contact, company=company,
            signals_top=signals_top, matched_criteria=matched, channel=channel,
        )

    row = _build_row_from_result(
        result, lead_id=int(lead_id), channel=channel, variant_id=variant_id,
    )
    msg_id: Optional[int] = None
    if not dry_run:
        msg_id = repos.outreach_messages.create(row)

    return {
        "lead_id": int(lead_id),
        "ok": True,
        "message_id": msg_id,
        "subject": row["subject"],
        "body": row["body"],
        "body_html": row["body_html"],
        "model": row["model"],
        "status": row["status"],
        "channel": row["channel"],
        "variant_id": variant_id,
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "generated_at": row["generated_at"],
        "persisted": not dry_run,
        "context": row["context"],
        "prompt": row["prompt"],
        "tier": lead.get("priority_tier"),
        "signal_count": len(signals_top),
    }


def run_outreach_batch(
    repos, *,
    project_id: Optional[int] = None,
    icp_id: Optional[int] = None,
    lead_ids: Optional[list[int]] = None,
    min_tier: str = "B",
    only_missing: bool = True,
    limit: int = 200,
    dry_run: bool = False,
    channel: str = "email",
    generator: Optional[OutreachGenerator] = None,
) -> dict:
    ids = _select_lead_ids(
        repos,
        project_id=project_id, icp_id=icp_id, lead_ids=lead_ids,
        min_tier=min_tier, only_missing=only_missing, limit=limit,
    )
    g = generator or get_default_outreach_generator()
    generated: list[dict] = []
    failed = 0
    persisted = 0
    skipped_below_tier = 0
    skipped_existing = 0
    for lid in ids:
        # Re-check tier per-lead (defense in depth) — the SQL already filtered.
        lead = repos.lead_candidates.get(lid)
        if not lead:
            failed += 1
            continue
        if not tier_meets_min(lead.get("priority_tier"), min_tier):
            skipped_below_tier += 1
            continue
        if only_missing and repos.outreach_messages.latest_for_lead(lid):
            skipped_existing += 1
            continue
        res = generate_outreach_for(
            repos, lid, generator=g, channel=channel, dry_run=dry_run,
        )
        if not res.get("ok"):
            failed += 1
            continue
        generated.append({
            "lead_id": res["lead_id"],
            "message_id": res.get("message_id"),
            "subject": res.get("subject"),
        })
        if res.get("persisted"):
            persisted += 1
    return {
        "scanned": len(ids),
        "generated": len(generated),
        "persisted": persisted,
        "failed": failed,
        "skipped_below_tier": skipped_below_tier,
        "skipped_existing": skipped_existing,
        "min_tier": min_tier.upper(),
        "channel": channel,
        "dry_run": dry_run,
        "lead_ids": ids,
        "items": generated,
    }


# ---------------------------------------------------------------------------
# Lifecycle (approve / edit)
# ---------------------------------------------------------------------------

def approve_message(repos, message_id: int) -> dict:
    msg = repos.outreach_messages.get(int(message_id))
    if not msg:
        return {"ok": False, "error": "message_not_found"}
    if msg.get("status") not in OUTREACH_STATUSES:
        return {"ok": False, "error": f"unknown_status:{msg.get('status')}"}
    repos.outreach_messages.update(int(message_id), {
        "status": "approved",
        "approved_at": _dt.datetime.utcnow().isoformat(timespec="seconds"),
    })
    return {"ok": True, "message_id": int(message_id), "status": "approved"}


def edit_message(repos, message_id: int, *,
                 subject: Optional[str] = None,
                 body: Optional[str] = None,
                 body_html: Optional[str] = None) -> dict:
    msg = repos.outreach_messages.get(int(message_id))
    if not msg:
        return {"ok": False, "error": "message_not_found"}
    payload: dict[str, Any] = {}
    if subject is not None:
        payload["subject"] = subject
    if body is not None:
        payload["body"] = body
    if body_html is not None:
        payload["body_html"] = body_html
    if not payload:
        return {"ok": False, "error": "no_changes"}
    repos.outreach_messages.update(int(message_id), payload)
    refreshed = repos.outreach_messages.get(int(message_id))
    return {"ok": True, "message_id": int(message_id), "message": refreshed}
