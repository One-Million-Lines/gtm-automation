"""Smoke test for repositories. Runs against a temp DB and prints PASS/FAIL.

Usage:
    python tests/test_repos_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT_DIR)

from db.sqlite_storage import SQLiteStorage
from repositories import RepoRegistry
from setup_database import apply_migrations


def assertion(cond: bool, msg: str, failures: list[str]) -> None:
    print(f"  {'OK' if cond else 'FAIL'}  {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    db_path = tmp.name
    print(f"Using temp DB: {db_path}")

    storage = SQLiteStorage(db_path)
    storage.run_script_file(f"{ROOT_DIR}/db/schema.sql")
    apply_migrations(storage, Path(f"{ROOT_DIR}/db/migrations"))

    repos = RepoRegistry(storage)

    print("\n[projects + icps]")
    project_id = repos.projects.create({"name": "Test Project", "description": "smoke"})
    assertion(project_id > 0, f"project created id={project_id}", failures)

    icp_id = repos.icps.create({
        "project_id": project_id,
        "name": "Shopify DTC EU",
        "target_industries": ["ecommerce", "DTC"],
        "competitors": ["Klaviyo"],
    })
    icp = repos.icps.get(icp_id)
    assertion(isinstance(icp["target_industries"], list), "icp.target_industries decoded as list", failures)
    assertion(icp["target_industries"] == ["ecommerce", "DTC"], "icp json roundtrip", failures)

    print("\n[companies + upsert_by_domain dedupe]")
    cid1 = repos.companies.upsert_by_domain({"name": "Acme", "domain": "acme.com", "status": "new"})
    cid2 = repos.companies.upsert_by_domain({"name": "Acme Inc", "domain": "acme.com", "status": "discovered"})
    assertion(cid1 == cid2, f"upsert deduped on domain (cid1={cid1}, cid2={cid2})", failures)
    assertion(repos.companies.count() == 1, "exactly 1 company", failures)
    co = repos.companies.get(cid1)
    assertion(co["status"] == "discovered", "upsert updated status", failures)

    cid3 = repos.companies.upsert_by_domain({"name": "Beta", "domain": "beta.com"})
    assertion(repos.companies.count() == 2, "second company added", failures)
    assertion(len(repos.companies.find_by_status("discovered")) == 1, "find_by_status works", failures)

    print("\n[contacts]")
    contact_id = repos.contacts.upsert_by_email({
        "company_id": cid1,
        "first_name": "Jane",
        "last_name": "Doe",
        "full_name": "Jane Doe",
        "email": "jane@acme.com",
        "email_status": "valid",
        "job_title": "Head of CRM",
        "normalized_role": "head_of_crm",
    })
    same = repos.contacts.upsert_by_email({"company_id": cid1, "email": "jane@acme.com", "job_title": "Head of CRM EU"})
    assertion(contact_id == same, "upsert_by_email deduped", failures)
    c = repos.contacts.get(contact_id)
    assertion(c["job_title"] == "Head of CRM EU", "contact updated via upsert", failures)

    print("\n[lead_candidates upsert]")
    lead_id = repos.lead_candidates.upsert(icp_id, cid1, contact_id, {
        "project_id": project_id,
        "lead_status": "new",
        "icp_fit_score": 0.8,
    })
    again = repos.lead_candidates.upsert(icp_id, cid1, contact_id, {
        "project_id": project_id,
        "lead_status": "scored",
        "final_score": 75,
    })
    assertion(lead_id == again, "lead_candidate upsert deduped", failures)
    assertion(repos.lead_candidates.count() == 1, "exactly 1 lead_candidate", failures)

    # company-only lead (contact_id IS NULL) handled in code
    lead2 = repos.lead_candidates.upsert(icp_id, cid3, None, {
        "project_id": project_id, "lead_status": "new",
    })
    lead2b = repos.lead_candidates.upsert(icp_id, cid3, None, {
        "project_id": project_id, "lead_status": "scored",
    })
    assertion(lead2 == lead2b, "company-only lead upsert deduped", failures)

    repos.lead_candidates.update(lead_id, {"ready_for_outreach": 1, "final_score": 80})
    ready = repos.lead_candidates.list_ready(project_id)
    assertion(len(ready) == 1 and ready[0]["id"] == lead_id, "list_ready returns the ready lead", failures)

    print("\n[signals + evidence]")
    sig_id = repos.signals.create({
        "company_id": cid1,
        "icp_id": icp_id,
        "signal_type": "tech_stack",
        "signal_name": "Uses Klaviyo",
        "raw_data": {"detected_via": "homepage_html"},
        "strength_score": 0.8,
        "confidence_score": 0.9,
    })
    sig = repos.signals.find_one({"id": sig_id})
    assertion(isinstance(sig["raw_data"], dict), "signal.raw_data decoded", failures)
    ev_id = repos.signal_evidence.create({
        "signal_id": sig_id,
        "evidence_type": "url",
        "source_url": "https://acme.com",
        "snippet": "klaviyo.js",
        "fingerprint": "abc123",
    })
    assertion(ev_id > 0, "signal_evidence created", failures)
    # dup fingerprint should fail (unique index) — assert the unique index works
    try:
        repos.signal_evidence.create({
            "signal_id": sig_id, "evidence_type": "url", "source_url": "x",
            "snippet": "x", "fingerprint": "abc123",
        })
        dup_blocked = False
    except Exception:
        dup_blocked = True
    assertion(dup_blocked, "duplicate evidence fingerprint rejected", failures)

    print("\n[email_drafts + latest_for_lead]")
    d1 = repos.email_drafts.create({
        "lead_candidate_id": lead_id, "subject": "v1", "body": "b1",
        "source_evidence": [{"type": "tech_stack", "claim": "uses klaviyo", "confidence": 0.9}],
    })
    d2 = repos.email_drafts.create({
        "lead_candidate_id": lead_id, "subject": "v2", "body": "b2", "approved": 1,
    })
    latest = repos.email_drafts.latest_for_lead(lead_id)
    assertion(latest["id"] == d2, "latest_for_lead returns newest", failures)
    approved = repos.email_drafts.find_approved_for_lead(lead_id)
    assertion(approved and approved["id"] == d2, "find_approved_for_lead works", failures)
    d1_row = repos.email_drafts.get(d1)
    assertion(isinstance(d1_row["source_evidence"], list), "email draft json roundtrip", failures)

    print("\n[suppression]")
    repos.suppression.add("domain", "spam.com", reason="test")
    repos.suppression.add("domain", "spam.com", reason="dup-add")  # idempotent
    assertion(repos.suppression.count() == 1, "suppression dedupe via unique index", failures)
    assertion(repos.suppression.is_suppressed("domain", "spam.com"), "is_suppressed true", failures)
    assertion(not repos.suppression.is_suppressed("domain", "ok.com"), "is_suppressed false", failures)
    repos.suppression.bulk_add([
        {"suppression_type": "email", "value": "x@y.com"},
        {"suppression_type": "email", "value": "x@y.com"},  # ignored
        {"suppression_type": "domain", "value": "another.com"},
    ])
    assertion(repos.suppression.count() == 3, "bulk_add added 2 unique entries", failures)

    print("\n[knowledge search]")
    repos.knowledge.create({
        "project_id": project_id, "icp_id": icp_id, "item_type": "objection",
        "title": "Price", "content": "too expensive", "tags": ["pricing", "objection"],
        "importance_score": 0.7,
    })
    repos.knowledge.create({
        "project_id": project_id, "item_type": "winning_message",
        "title": "Hook", "content": "x", "tags": ["hook"], "importance_score": 0.9,
    })
    found = repos.knowledge.search(project_id, tags=["pricing"])
    assertion(len(found) == 1 and found[0]["title"] == "Price", "knowledge.search by tag", failures)
    found_icp = repos.knowledge.search(project_id, icp_id=icp_id)
    assertion(len(found_icp) == 1, "knowledge.search by icp", failures)

    print("\n[pipeline run + step + log]")
    run_id = repos.pipeline_runs.start(project_id, icp_id, "full_pipeline", {"dry_run": True})
    step_id = repos.pipeline_run_steps.start(run_id, "CompanyDiscoveryModule")
    repos.module_logs.log(
        pipeline_run_id=run_id, pipeline_run_step_id=step_id,
        module_name="CompanyDiscoveryModule", level="info",
        message="discovered_companies", context={"count": 42},
    )
    repos.pipeline_run_steps.finish(step_id, status="completed", input_count=10, output_count=42)
    repos.pipeline_runs.finish(run_id, "completed", total_processed=10, total_created=42)
    run = repos.pipeline_runs.get(run_id)
    step = repos.pipeline_run_steps.get(step_id)
    log = repos.module_logs.find_one({"pipeline_run_step_id": step_id})
    assertion(run["status"] == "completed" and run["finished_at"] is not None, "run finished", failures)
    assertion(step["status"] == "completed" and step["output_count"] == 42, "step finished w/ counts", failures)
    assertion(log and log["context"]["count"] == 42, "log context json roundtrip", failures)
    assertion(isinstance(run["config"], dict) and run["config"]["dry_run"] is True, "run.config json roundtrip", failures)

    print("\n[exports]")
    batch_id = repos.exports.create_batch({
        "project_id": project_id, "icp_id": icp_id, "name": "Batch 1",
        "format": "instantly_csv", "filters": {"min_score": 70},
    })
    repos.exports.add_row(batch_id, lead_id, email="jane@acme.com", email_draft_id=d2,
                          payload={"subject": "v2", "body": "b2"})
    assertion(repos.exports.has_been_exported(lead_id), "has_been_exported true", failures)
    assertion(not repos.exports.has_been_exported(99999), "has_been_exported false", failures)
    repos.exports.finish_batch(batch_id, status="completed", row_count=1, file_path="/tmp/x.csv")
    b = repos.exports.batches.get(batch_id)
    assertion(b["status"] == "completed" and b["row_count"] == 1, "batch finished", failures)
    assertion(isinstance(b["filters"], dict), "batch.filters json roundtrip", failures)

    print("\n[update auto-touches updated_at]")
    co_before = repos.companies.get(cid1)
    repos.companies.update(cid1, {"city": "Cluj"})
    co_after = repos.companies.get(cid1)
    assertion(co_after["updated_at"] >= co_before["updated_at"], "updated_at advanced (or equal)", failures)
    assertion(co_after["city"] == "Cluj", "company city updated", failures)

    storage.close()
    os.unlink(db_path)

    print("\n" + "=" * 60)
    if failures:
        print(f"FAIL — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — all assertions OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
