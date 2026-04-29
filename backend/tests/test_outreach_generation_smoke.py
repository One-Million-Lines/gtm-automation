"""Smoke test for File 13 — outreach generation (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.outreach_generator import (
    FakeOutreachGenerator, OUTREACH_STATUSES, _render_prompt,
    _top_signal_contributions, set_default_outreach_generator, tier_meets_min,
)
from services.outreach_service import (
    approve_message, edit_message, generate_outreach_for, run_outreach_batch,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # ------------------------------------------------------------------
    print("\n[tier_meets_min]")
    assertion(tier_meets_min("A", "B"), "A meets B", failures)
    assertion(tier_meets_min("B", "B"), "B meets B", failures)
    assertion(not tier_meets_min("C", "B"), "C does not meet B", failures)
    assertion(not tier_meets_min(None, "B"), "None does not meet B", failures)

    # ------------------------------------------------------------------
    print("\n[_top_signal_contributions]")
    expl = {
        "intent": {
            "contributions": [
                {"signal_type": "hiring_intent", "contribution": 0.9},
                {"signal_type": "funding", "contribution": 0.8},
                {"signal_type": "linkedin_activity", "contribution": 0.1},
                {"signal_type": "news_mention", "contribution": 0.5},
            ]
        }
    }
    top = _top_signal_contributions(expl, n=3)
    assertion(len(top) == 3, f"top3 len={len(top)}", failures)
    assertion(top[0]["signal_type"] == "hiring_intent", "top1 hiring_intent", failures)
    assertion(top[1]["signal_type"] == "funding", "top2 funding", failures)
    assertion(_top_signal_contributions(None) == [], "None -> []", failures)

    # ------------------------------------------------------------------
    print("\n[_render_prompt grounding]")
    icp = {"value_proposition": "boost outbound conversions", "outreach_angle": "warm intro",
           "pain_points": ["low reply rate", "manual research"]}
    company = {"name": "AcmeCo", "industry": "saas"}
    contact = {"first_name": "Alex", "job_title": "CTO"}
    prompt = _render_prompt(
        icp=icp, lead={}, contact=contact, company=company,
        signals_top=top, matched_criteria=["industry", "role"], channel="email",
    )
    assertion("AcmeCo" in prompt, "company name in prompt", failures)
    assertion("Alex" in prompt, "first_name in prompt", failures)
    assertion("CTO" in prompt, "job_title in prompt", failures)
    assertion("boost outbound conversions" in prompt, "value_prop in prompt", failures)
    assertion("hiring_intent" in prompt, "top signal type in prompt", failures)
    assertion("industry, role" in prompt, "matched criteria in prompt", failures)

    # ------------------------------------------------------------------
    print("\n[FakeOutreachGenerator install]")
    fake = FakeOutreachGenerator()
    set_default_outreach_generator(fake)

    # ------------------------------------------------------------------
    print("\n[db scenario setup]")
    pid = repos.projects.create({"name": "smoke13"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP1", "status": "draft",
        "target_industries": ["saas"], "target_roles": ["cto"],
        "target_seniorities": ["c_level"], "target_geographies": ["germany"],
        "target_company_size_min": 10, "target_company_size_max": 200,
        "value_proposition": "boost outbound reply rates by 3x",
        "outreach_angle": "warm intro for saas CTOs",
        "pain_points": ["low reply rate", "manual prospect research"],
    })
    co_a = repos.companies.create({
        "name": "AcmeCo", "domain": "acmeco.example", "industry": "saas",
        "country": "Germany", "employee_count": 50, "status": "discovered",
    })
    co_b = repos.companies.create({
        "name": "PoorFitCo", "domain": "poorfit.example", "industry": "retail",
        "country": "USA", "employee_count": 5, "status": "discovered",
    })
    ct_a = repos.contacts.create({
        "company_id": co_a, "first_name": "Alex", "last_name": "X", "full_name": "Alex X",
        "job_title": "CTO", "normalized_role": "cto", "email": "alex@acmeco.example",
        "country": "Germany", "status": "new",
    })
    ct_b = repos.contacts.create({
        "company_id": co_b, "first_name": "Sam", "last_name": "Y", "full_name": "Sam Y",
        "job_title": "Sales Rep", "normalized_role": "sales", "email": "sam@poorfit.example",
        "country": "USA", "status": "new",
    })
    # tier-A lead
    lead_a = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co_a, "contact_id": ct_a, "lead_status": "scored",
        "icp_fit_score": 1.0, "signal_score": 0.9, "final_score": 0.96,
        "priority_tier": "A", "scored_at": "2026-01-01T00:00:00",
        "scoring_explanation": {
            "fit": {"matched": ["industry", "role", "seniority", "geo", "size"]},
            "intent": {"contributions": [
                {"signal_type": "hiring_intent", "strength": 0.9, "recency": 1.0,
                 "contribution": 0.9, "weight": 1.0},
                {"signal_type": "funding", "strength": 0.8, "recency": 0.9,
                 "contribution": 0.7, "weight": 1.0},
            ]},
        },
    })
    # tier-D lead (should be skipped at min_tier=B)
    lead_d = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co_b, "contact_id": ct_b, "lead_status": "scored",
        "icp_fit_score": 0.1, "signal_score": 0.0, "final_score": 0.06,
        "priority_tier": "D", "scored_at": "2026-01-01T00:00:00",
        "scoring_explanation": {"fit": {"matched": []}, "intent": {"contributions": []}},
    })

    # ------------------------------------------------------------------
    print("\n[generate_outreach_for tier-A lead]")
    r = generate_outreach_for(repos, lead_a)
    assertion(r["ok"], f"ok={r.get('ok')} err={r.get('error')}", failures)
    assertion(bool(r.get("subject")), "subject populated", failures)
    assertion("Alex" in r["body"], "body contains first_name", failures)
    assertion("AcmeCo" in r["body"], "body contains company name", failures)
    assertion("hiring" in r["body"].lower(), "body references hiring signal", failures)
    assertion(r["status"] == "draft", "status=draft", failures)
    assertion(r["persisted"] is True, "persisted", failures)
    msg_a = r["message_id"]
    refetch = repos.outreach_messages.get(msg_a)
    assertion(refetch is not None, "row persisted", failures)
    assertion(refetch["status"] == "draft", "refetched draft", failures)
    assertion("AcmeCo" in (refetch["prompt"] or ""), "prompt persisted with company", failures)
    assertion(isinstance(refetch.get("context"), dict), "context decoded as dict", failures)
    assertion(refetch["context"]["channel"] == "email", "context.channel=email", failures)

    # ------------------------------------------------------------------
    print("\n[skip leads below min_tier in batch]")
    batch = run_outreach_batch(repos, project_id=pid, min_tier="B", only_missing=True)
    # tier-A already has a draft -> skipped_existing; tier-D below min_tier -> filtered out by SQL
    assertion(batch["scanned"] == 0, f"scanned tier>=B unscored=0 -> {batch['scanned']}", failures)
    assertion(batch["generated"] == 0, "no generation when tier-A already drafted", failures)

    # only_missing=False should regenerate for tier-A but still skip tier-D
    batch2 = run_outreach_batch(repos, project_id=pid, min_tier="B", only_missing=False)
    assertion(batch2["scanned"] == 1, f"only tier>=B counted -> {batch2['scanned']}", failures)
    assertion(batch2["generated"] == 1, "generated for tier-A", failures)
    # ensure history grew on lead_a
    history = repos.outreach_messages.history_for_lead(lead_a)
    assertion(len(history) >= 2, f"history grew >=2 -> {len(history)}", failures)

    # min_tier=D should pick up the tier-D lead too
    batch3 = run_outreach_batch(repos, project_id=pid, min_tier="D", only_missing=True)
    # tier-D not yet drafted, so should generate exactly 1 here
    assertion(batch3["generated"] >= 1, f"min_tier=D includes tier-D -> {batch3['generated']}", failures)

    # ------------------------------------------------------------------
    print("\n[dry_run no-write]")
    before_count = len(repos.outreach_messages.history_for_lead(lead_a))
    dr = generate_outreach_for(repos, lead_a, dry_run=True)
    after_count = len(repos.outreach_messages.history_for_lead(lead_a))
    assertion(dr["persisted"] is False, "persisted=False", failures)
    assertion(after_count == before_count, "history unchanged", failures)

    # ------------------------------------------------------------------
    print("\n[approve transition]")
    ap = approve_message(repos, msg_a)
    assertion(ap["ok"], "approve ok", failures)
    refetch_ap = repos.outreach_messages.get(msg_a)
    assertion(refetch_ap["status"] == "approved", "status=approved", failures)
    assertion(refetch_ap["approved_at"] is not None, "approved_at set", failures)

    # ------------------------------------------------------------------
    print("\n[edit transition]")
    ed = edit_message(repos, msg_a, subject="EDITED subject", body="EDITED body")
    assertion(ed["ok"], "edit ok", failures)
    refetch_ed = repos.outreach_messages.get(msg_a)
    assertion(refetch_ed["subject"] == "EDITED subject", "subject persisted", failures)
    assertion(refetch_ed["body"] == "EDITED body", "body persisted", failures)
    no_change = edit_message(repos, msg_a)
    assertion(not no_change["ok"], "no_changes -> not ok", failures)

    # ------------------------------------------------------------------
    print("\n[404 paths]")
    r404 = generate_outreach_for(repos, 999999)
    assertion(not r404["ok"] and r404["error"] == "lead_not_found", "missing lead", failures)
    ap404 = approve_message(repos, 999999)
    assertion(not ap404["ok"], "missing message approve", failures)
    ed404 = edit_message(repos, 999999, subject="x")
    assertion(not ed404["ok"], "missing message edit", failures)

    # ------------------------------------------------------------------
    print("\n[taxonomy guard]")
    assertion("draft" in OUTREACH_STATUSES and "approved" in OUTREACH_STATUSES
              and "sent" in OUTREACH_STATUSES, "statuses present", failures)
    assertion("rejected" not in OUTREACH_STATUSES, "rejected not in taxonomy", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=outreach_generation]")
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="outreach_generation",
        config={"only_missing": False, "min_tier": "B", "limit": 20},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

    # restore default generator
    set_default_outreach_generator(None)

    # ------------------------------------------------------------------
    print("\n========")
    if failures:
        print(f"FAIL — {len(failures)} failure(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — 0 failures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
