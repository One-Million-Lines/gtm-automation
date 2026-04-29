"""Smoke test for File 11 — signal extraction (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.signal_extraction_service import (
    extract_company_signals_for, extract_contact_signals_for, run_signals_batch,
)
from services.signal_provider import (
    DetectedSignal, FakeSignalProvider, SIGNAL_TYPES,
    diff_tech_stack, set_default_signal_provider,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # ------------------------------------------------------------------
    print("\n[diff_tech_stack]")
    diff = diff_tech_stack(["a", "b", "c"], ["b", "c", "d"])
    assertion(diff == {"added": ["d"], "removed": ["a"]}, "diff added/removed", failures)
    diff2 = diff_tech_stack(None, ["x"])
    assertion(diff2 == {"added": ["x"], "removed": []}, "None prev -> all added", failures)

    # ------------------------------------------------------------------
    print("\n[FakeSignalProvider config]")
    fake = FakeSignalProvider()
    fake.for_company(1, [DetectedSignal(
        signal_type="hiring_intent", signal_name="careers_page",
        description="careers reachable", source_url="https://acme.com/careers",
        strength_score=0.6, confidence_score=0.7,
        raw_data={"job_hint_count": 7},
    )])
    fake.for_contact(1, [DetectedSignal(
        signal_type="role_change", signal_name="job_title_changed",
        description="vp eng -> svp eng", strength_score=0.7,
    )])
    set_default_signal_provider(fake)

    # ------------------------------------------------------------------
    print("\n[db scenario setup]")
    pid = repos.projects.create({"name": "smoke11"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP1", "status": "draft",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co_id = repos.companies.create({
        "project_id": pid, "name": "Acme", "domain": "acme.com",
        "status": "discovered",
    })
    # two enrichments — to exercise tech_stack_change + hiring_pace + social_bump
    repos.company_enrichment.create({
        "company_id": co_id, "provider": "website_homepage",
        "tech_stack": ["shopify"], "employee_count": 50,
        "social_links": ["https://linkedin.com/company/acme"],
        "raw_data": {}, "confidence_score": 0.6,
    })
    repos.company_enrichment.create({
        "company_id": co_id, "provider": "website_homepage",
        "tech_stack": ["shopify", "klaviyo"], "employee_count": 70,
        "social_links": ["https://linkedin.com/company/acme",
                          "https://twitter.com/acme"],
        "raw_data": {}, "confidence_score": 0.6,
    })
    contact_id = repos.contacts.create({
        "company_id": co_id, "first_name": "Alex", "last_name": "Doe",
        "email": "alex@acme.com", "job_title": "Head of Eng",
        "linkedin_url": "https://linkedin.com/in/alex", "status": "new",
    })
    # lead candidate so project-scoped contact selection works
    repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co_id, "contact_id": contact_id, "status": "new",
    })

    # ------------------------------------------------------------------
    print(f"\n[extract_company_signals_for company={co_id}]")
    res = extract_company_signals_for(repos, co_id, icp_id=icp_id)
    assertion(res["ok"] is True, "ok", failures)
    types = sorted({s["signal_type"] for s in res["signals"]})
    print(f"   types -> {types}")
    assertion("hiring_intent" in types, "fake hiring_intent persisted", failures)
    assertion("tech_stack_change" in types, "tech_stack_change derived", failures)
    assertion("hiring_pace" in types, "hiring_pace derived", failures)
    assertion("social_activity" in types, "social_activity derived", failures)
    assertion(res["persisted"] >= 4, f"persisted>=4 -> {res['persisted']}", failures)

    # ------------------------------------------------------------------
    print(f"\n[extract_contact_signals_for contact={contact_id}]")
    cres = extract_contact_signals_for(repos, contact_id, icp_id=icp_id)
    assertion(cres["ok"], "contact ok", failures)
    assertion(cres["persisted"] >= 1, f"persisted >=1 -> {cres['persisted']}", failures)
    sig_types = {s["signal_type"] for s in cres["signals"]}
    assertion("role_change" in sig_types, "role_change present", failures)

    # ------------------------------------------------------------------
    print("\n[only_missing skip]")
    again = extract_company_signals_for(repos, co_id, icp_id=icp_id, only_missing=True)
    assertion(again["skipped"] is True, "second call skipped", failures)
    assertion(again.get("error") == "already_has_signals", "skip reason", failures)

    # ------------------------------------------------------------------
    print("\n[dry_run no-write]")
    before = repos.signals.count({"company_id": co_id})
    dr = extract_company_signals_for(repos, co_id, icp_id=icp_id,
                                     only_missing=False, dry_run=True)
    after = repos.signals.count({"company_id": co_id})
    assertion(after == before, f"no new rows ({before} -> {after})", failures)
    assertion(dr["persisted"] == 0, "persisted=0 in dry_run", failures)
    assertion(dr["detected"] >= 1, "detected still >=1", failures)

    # ------------------------------------------------------------------
    print("\n[run_signals_batch by project_id]")
    # reset by deleting signals so only_missing=False re-runs
    batch = run_signals_batch(
        repos, project_id=pid, icp_id=icp_id,
        only_missing=False, limit=20,
    )
    print(f"   companies={batch['scanned_companies']} contacts={batch['scanned_contacts']} "
          f"persisted={batch['persisted']} failed={batch['failed']}")
    assertion(batch["scanned_companies"] == 1, "scanned 1 company", failures)
    assertion(batch["scanned_contacts"] == 1, "scanned 1 contact (via lead_candidates)", failures)
    assertion(batch["failed"] == 0, "no failures", failures)
    assertion(batch["persisted"] >= 5, f"persisted>=5 -> {batch['persisted']}", failures)

    # ------------------------------------------------------------------
    print("\n[signal_types filter]")
    filt = run_signals_batch(
        repos, project_id=pid, icp_id=icp_id,
        signal_types=["tech_stack_change"], only_missing=False, limit=20,
    )
    persisted_types = {s["signal_type"] for r in filt["company_results"]
                       for s in r.get("signals", [])}
    print(f"   persisted_types -> {persisted_types}")
    assertion(persisted_types <= {"tech_stack_change"},
              "filter limits to tech_stack_change", failures)

    # ------------------------------------------------------------------
    print("\n[unknown signal_type taxonomy guard]")
    bad = "totally_made_up"
    assertion(bad not in SIGNAL_TYPES, "taxonomy excludes bogus type", failures)

    # ------------------------------------------------------------------
    print("\n[404 paths]")
    miss = extract_company_signals_for(repos, 9999, icp_id=icp_id)
    assertion(miss["skipped"] and miss.get("error") == "company_not_found",
              "missing company -> skipped", failures)
    miss2 = extract_contact_signals_for(repos, 9999, icp_id=icp_id)
    assertion(miss2["skipped"] and miss2.get("error") == "contact_not_found",
              "missing contact -> skipped", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=signal_extraction]")
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="signal_extraction",
        config={"only_missing": False, "limit": 20},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

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
