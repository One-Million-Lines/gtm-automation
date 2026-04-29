"""Smoke test for File 12 — lead scoring (no real network)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.lead_scorer import (
    FIT_WEIGHTS, FakeLeadScorer, RuleBasedLeadScorer, SIGNAL_WEIGHTS,
    PRIORITY_TIERS, aggregate_signals, compute_fit, set_default_lead_scorer,
    tier_for,
)
from services.lead_scoring_service import run_scoring_batch, score_lead_for


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # ------------------------------------------------------------------
    print("\n[FIT_WEIGHTS sum to 1.0]")
    total = round(sum(FIT_WEIGHTS.values()), 4)
    assertion(total == 1.0, f"sum={total}", failures)

    # ------------------------------------------------------------------
    print("\n[tier_for thresholds]")
    assertion(tier_for(0.95) == "A", "0.95 -> A", failures)
    assertion(tier_for(0.60) == "B", "0.60 -> B", failures)
    assertion(tier_for(0.40) == "C", "0.40 -> C", failures)
    assertion(tier_for(0.10) == "D", "0.10 -> D", failures)

    # ------------------------------------------------------------------
    print("\n[compute_fit isolated]")
    icp = {
        "target_industries": ["saas"],
        "target_roles": ["cto"],
        "target_seniorities": ["c_level"],
        "target_geographies": ["germany"],
        "target_company_size_min": 10,
        "target_company_size_max": 200,
    }
    co = {"industry": "SaaS", "country": "Germany", "employee_count": 50}
    ct = {"job_title": "CTO", "normalized_role": "cto", "country": "Germany"}
    fit, parts = compute_fit(icp, co, ct)
    assertion(fit == 1.0, f"perfect fit -> {fit}", failures)
    assertion(all(p["matched"] for p in parts.values()), "all parts matched", failures)
    fit2, parts2 = compute_fit(icp, {"industry": "ecommerce", "employee_count": 1000}, None)
    assertion(fit2 < 0.4, f"poor fit -> {fit2}", failures)

    # ------------------------------------------------------------------
    print("\n[aggregate_signals weights + recency decay]")
    now = _dt.datetime.utcnow()
    fresh = {
        "id": 1, "signal_type": "hiring_intent",
        "strength_score": 1.0,
        "created_at": now.isoformat(timespec="seconds"),
    }
    old = {
        "id": 2, "signal_type": "hiring_intent",
        "strength_score": 1.0,
        "created_at": (now - _dt.timedelta(days=120)).isoformat(timespec="seconds"),
    }
    score_fresh, _ = aggregate_signals([fresh], now=now)
    score_old, _ = aggregate_signals([old], now=now)
    assertion(score_fresh > score_old, f"recency decay {score_fresh:.3f} > {score_old:.3f}", failures)
    score_high, _ = aggregate_signals([{
        "id": 3, "signal_type": "funding", "strength_score": 1.0,
        "created_at": now.isoformat(timespec="seconds"),
    }], now=now)
    score_low, _ = aggregate_signals([{
        "id": 4, "signal_type": "linkedin_activity", "strength_score": 1.0,
        "created_at": now.isoformat(timespec="seconds"),
    }], now=now)
    assertion(abs(score_high - score_low) < 1e-7,
              "single-signal aggregator normalizes by weight (both 1.0)", failures)

    # ------------------------------------------------------------------
    print("\n[RuleBasedLeadScorer end-to-end]")
    rbs = RuleBasedLeadScorer()
    res = rbs.score(icp=icp, company=co, contact=ct, signals=[fresh])
    assertion(res.fit_score == 1.0, f"fit={res.fit_score}", failures)
    assertion(res.intent_score > 0.0, f"intent>0 -> {res.intent_score}", failures)
    assertion(res.priority_tier in PRIORITY_TIERS, f"tier={res.priority_tier}", failures)
    assertion(res.explanation["scorer"] == "rule_based", "scorer label", failures)
    assertion("matched" in res.explanation["fit"], "fit.matched present", failures)
    assertion("contributions" in res.explanation["intent"], "intent.contributions present", failures)

    # ------------------------------------------------------------------
    print("\n[FakeLeadScorer override + install]")
    fake = FakeLeadScorer(fixed_fit=0.8, fixed_intent=0.9, use_rules_fallback=False)
    set_default_lead_scorer(fake)

    # ------------------------------------------------------------------
    print("\n[db scenario setup]")
    pid = repos.projects.create({"name": "smoke12"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP1", "status": "draft",
        "target_industries": ["saas"], "target_roles": ["cto"],
        "target_seniorities": ["c_level"], "target_geographies": ["germany"],
        "target_company_size_min": 10, "target_company_size_max": 200,
    })
    co_a = repos.companies.create({
        "name": "Acme SaaS", "domain": "acme.example", "industry": "saas",
        "country": "Germany", "employee_count": 50, "status": "discovered",
    })
    co_b = repos.companies.create({
        "name": "Big Retail", "domain": "bigretail.example", "industry": "retail",
        "country": "USA", "employee_count": 5000, "status": "discovered",
    })
    ct_a = repos.contacts.create({
        "company_id": co_a, "first_name": "A", "last_name": "X", "full_name": "A X",
        "job_title": "CTO", "normalized_role": "cto", "email": "a@acme.example",
        "country": "Germany", "status": "new",
    })
    ct_b = repos.contacts.create({
        "company_id": co_b, "first_name": "B", "last_name": "Y", "full_name": "B Y",
        "job_title": "Sales Rep", "normalized_role": "sales", "email": "b@bigretail.example",
        "country": "USA", "status": "new",
    })
    lead_a = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co_a, "contact_id": ct_a, "lead_status": "new",
    })
    lead_b = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co_b, "contact_id": ct_b, "lead_status": "new",
    })
    # add a couple of signals on co_a
    repos.signals.create({
        "company_id": co_a, "icp_id": icp_id, "project_id": pid,
        "signal_type": "hiring_intent", "signal_name": "careers",
        "strength_score": 0.9, "confidence_score": 0.8,
        "detected_by": "test", "raw_data": {},
    })

    # ------------------------------------------------------------------
    print("\n[score_lead_for fake scorer]")
    r = score_lead_for(repos, lead_a)
    assertion(r["ok"], "ok", failures)
    assertion(r["fit_score"] == 0.8, f"fit forced=0.8 -> {r['fit_score']}", failures)
    assertion(r["intent_score"] == 0.9, f"intent forced=0.9 -> {r['intent_score']}", failures)
    expected_combined = round(0.6 * 0.8 + 0.4 * 0.9, 4)
    assertion(r["combined_score"] == expected_combined,
              f"combined={r['combined_score']} expected={expected_combined}", failures)
    assertion(r["priority_tier"] == "A", f"tier=A -> {r['priority_tier']}", failures)
    refetch = repos.lead_candidates.get(lead_a)
    assertion(refetch["priority_tier"] == "A", "persisted tier=A", failures)
    assertion(refetch["scored_at"], "scored_at persisted", failures)
    assertion(isinstance(refetch["scoring_explanation"], dict),
              "scoring_explanation parsed as dict", failures)

    # ------------------------------------------------------------------
    print("\n[only_missing skips already-scored]")
    batch_skip = run_scoring_batch(repos, project_id=pid, only_missing=True)
    assertion(batch_skip["scanned"] == 1, f"scans only unscored -> {batch_skip['scanned']}", failures)
    assertion(batch_skip["scored"] == 1, "scored 1 (lead_b)", failures)

    # ------------------------------------------------------------------
    print("\n[dry_run no-write]")
    before = repos.lead_candidates.get(lead_a)["scored_at"]
    dr = score_lead_for(repos, lead_a, dry_run=True)
    after = repos.lead_candidates.get(lead_a)["scored_at"]
    assertion(after == before, "dry_run unchanged", failures)
    assertion(dr["persisted"] is False, "persisted=False in dry_run", failures)

    # ------------------------------------------------------------------
    print("\n[batch by project_id, only_missing=False]")
    batch = run_scoring_batch(repos, project_id=pid, only_missing=False)
    assertion(batch["scanned"] == 2, f"scanned=2 -> {batch['scanned']}", failures)
    assertion(batch["scored"] == 2, f"scored=2 -> {batch['scored']}", failures)
    assertion(batch["failed"] == 0, "no failures", failures)
    assertion(sum(batch["tier_counts"].values()) == 2,
              f"tier_counts sum=2 -> {batch['tier_counts']}", failures)

    # ------------------------------------------------------------------
    print("\n[404 path]")
    miss = score_lead_for(repos, 999999)
    assertion(miss["ok"] is False, "missing lead -> ok=False", failures)
    assertion(miss.get("error") == "lead_not_found", f"err -> {miss.get('error')}", failures)

    # ------------------------------------------------------------------
    print("\n[taxonomy guard — tier]")
    assertion("Z" not in PRIORITY_TIERS, "Z not a valid tier", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=lead_scoring]")
    # reset by re-running with only_missing=False through pipeline
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="lead_scoring",
        config={"only_missing": False, "limit": 20},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

    # restore default scorer (no-op; later tests fresh)
    set_default_lead_scorer(None)

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
