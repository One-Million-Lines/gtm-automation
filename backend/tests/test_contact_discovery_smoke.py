"""Smoke test for contact discovery. Temp DB. PASS/FAIL.

Usage:
    python tests/test_contact_discovery_smoke.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT_DIR)

from db.sqlite_storage import SQLiteStorage
from pipeline import PipelineRunner
from repositories import RepoRegistry
from services.company_discovery_service import ingest_company_record
from services.contact_discovery_service import (
    ingest_contact_record, ingest_contact_records, merge_contact_payload,
    normalize_contact,
)
from services.role_matcher import match_role
from setup_database import apply_migrations
from vtutils.vtlogger import initLog


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
    vtlog = initLog("contact_discovery_smoke")

    # ─────────────────────────────────────────────────────────────
    print("\n[1/9 match_role]")
    personas = ["CMO", "Head of CRM", "Lifecycle Marketing Manager"]
    r = match_role("CMO at Acme", personas)
    assertion(r["is_match"] and r["normalized_role"] == "marketing_lead" and r["priority"] == 1,
              f"CMO -> {r}", failures)
    r = match_role("Head of CRM", personas)
    assertion(r["is_match"] and r["normalized_role"] == "crm_lead" and r["priority"] == 2,
              f"Head of CRM -> {r}", failures)
    r = match_role("Software Engineer", personas)
    assertion(not r["is_match"], f"Software Engineer -> {r}", failures)
    r = match_role("Founder & CEO", personas)
    assertion(r["is_match"] and r["normalized_role"] == "founder",
              f"Founder & CEO -> {r}", failures)
    r = match_role("Email Marketing Manager", personas)
    assertion(r["is_match"] and r["normalized_role"] == "email_marketing",
              f"Email Marketing Manager -> {r}", failures)
    r = match_role("", personas)
    assertion(not r["is_match"], f"empty -> {r}", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[2/9 normalize_contact]")
    n = normalize_contact({
        "first_name": "Jane", "last_name": "Doe",
        "email": "Jane.Doe@Example.COM",
        "job_title": "  CMO  ",
        "linkedin_url": "https://linkedin.com/in/janedoe",
    }, company_id=42)
    assertion(n["full_name"] == "Jane Doe", f"full_name -> {n.get('full_name')}", failures)
    assertion(n["email"] == "jane.doe@example.com", f"email -> {n.get('email')}", failures)
    assertion(n["company_id"] == 42 and n["job_title"] == "CMO",
              f"company_id/job_title -> {n}", failures)
    n2 = normalize_contact({"email": "not-an-email"}, company_id=1)
    assertion("email" not in n2, f"invalid email dropped -> {n2}", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[merge_contact_payload]")
    merged = merge_contact_payload(
        {"first_name": "Jane", "job_title": "CMO", "city": "Paris", "email": "j@a.com"},
        {"first_name": "", "job_title": "VP Marketing", "country": "FR", "email": ""},
    )
    assertion(merged["first_name"] == "Jane", f"keeps existing first_name -> {merged}", failures)
    assertion(merged["job_title"] == "VP Marketing", f"overwrites job_title -> {merged}", failures)
    assertion(merged["country"] == "FR", f"fills country -> {merged}", failures)

    # ─────────────────────────────────────────────────────────────
    project_id = repos.projects.create({"name": "P"})
    icp_id = repos.icps.create({
        "project_id": project_id, "name": "ICP",
        "target_industries": ["saas"],
        "target_personas": ["CMO", "Head of CRM"],
        "target_roles": ["cto"],
    })

    # Pre-create 2 companies via company_discovery service.
    ingest_company_record(repos, project_id=project_id, icp_id=icp_id,
                          source_name="manual", raw={"name": "Acme", "domain": "acme.com"})
    ingest_company_record(repos, project_id=project_id, icp_id=icp_id,
                          source_name="manual", raw={"name": "Beta", "domain": "beta.io"})
    acme = repos.companies.find_one({"domain": "acme.com"})
    beta = repos.companies.find_one({"domain": "beta.io"})

    # ─────────────────────────────────────────────────────────────
    print("\n[3/9 ingest 3 records (2 created, 1 skipped no-company)]")
    summary = ingest_contact_records(
        repos, project_id=project_id, icp_id=icp_id,
        source_name="manual", source_type="manual",
        records=[
            {"first_name": "Jane", "last_name": "Doe", "email": "jane@acme.com",
             "job_title": "CMO", "company_id": acme["id"]},
            {"first_name": "Bob", "last_name": "Smith", "email": "bob@beta.io",
             "job_title": "Head of CRM", "company_domain": "https://www.beta.io"},
            {"first_name": "Nope", "email": "nope@unknown.com"},  # no company resolvable
        ],
        target_personas=["CMO", "Head of CRM"],
    )
    assertion(summary["created"] == 2 and summary["skipped"] == 1,
              f"summary -> {summary}", failures)
    assertion(repos.contacts.count({}) == 2, "2 contacts in DB", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[4/9 re-ingest same email -> updated]")
    r = ingest_contact_record(
        repos, project_id=project_id, icp_id=icp_id,
        company_id=int(acme["id"]), source_name="manual",
        raw={"email": "jane@acme.com", "first_name": "Jane", "last_name": "Doe",
             "job_title": "VP Marketing", "city": "Paris"},
        target_personas=["CMO", "Head of CRM"],
    )
    assertion(r["action"] == "updated", f"re-ingest -> {r}", failures)
    assertion(repos.contacts.count({}) == 2, "still 2 contacts", failures)
    jane = repos.contacts.get_by_email("jane@acme.com")
    assertion(jane["job_title"] == "VP Marketing" and jane["city"] == "Paris",
              f"jane updated -> {jane.get('job_title')}, {jane.get('city')}", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[5/9 lead_candidate placeholder attach]")
    # The placeholder created by company_discovery for (icp, acme, NULL) should
    # have been attached to jane on first ingest.
    placeholders = repos.lead_candidates.find({"icp_id": icp_id, "company_id": acme["id"], "contact_id": None})
    assertion(len(placeholders) == 0, f"no NULL-contact placeholder for acme remains -> {len(placeholders)}", failures)
    jane_leads = repos.lead_candidates.find({"icp_id": icp_id, "company_id": acme["id"], "contact_id": jane["id"]})
    assertion(len(jane_leads) == 1, f"jane has exactly 1 lead -> {len(jane_leads)}", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[6/9 dedupe by linkedin and by (company,name)]")
    ingest_contact_record(repos, project_id=project_id, icp_id=icp_id,
                          company_id=int(acme["id"]), source_name="manual",
                          raw={"first_name": "Lin", "last_name": "X",
                               "linkedin_url": "https://linkedin.com/in/linx",
                               "job_title": "Lifecycle Marketing Manager"})
    r2 = ingest_contact_record(repos, project_id=project_id, icp_id=icp_id,
                               company_id=int(acme["id"]), source_name="manual",
                               raw={"first_name": "Linus", "last_name": "Y",
                                    "linkedin_url": "https://linkedin.com/in/linx",
                                    "job_title": "Lifecycle Marketing"})
    assertion(r2["action"] == "updated", f"linkedin dedupe -> {r2['action']}", failures)
    # (company_id, full_name) dedupe — no email, no linkedin
    ingest_contact_record(repos, project_id=project_id, icp_id=icp_id,
                          company_id=int(beta["id"]), source_name="manual",
                          raw={"first_name": "Carl", "last_name": "Q",
                               "job_title": "CMO"})
    r3 = ingest_contact_record(repos, project_id=project_id, icp_id=icp_id,
                               company_id=int(beta["id"]), source_name="manual",
                               raw={"full_name": "carl q", "job_title": "Head of Marketing"})
    assertion(r3["action"] == "updated", f"(company,name) dedupe -> {r3['action']}", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[7/9 company_domain resolver]")
    s2 = ingest_contact_records(
        repos, project_id=project_id, icp_id=icp_id,
        source_name="csv-2", source_type="csv",
        records=[
            {"first_name": "Dom", "email": "dom@beta.io",
             "company_domain": "https://www.beta.io/about"},
            {"first_name": "Ghost", "email": "ghost@nowhere.com",
             "company_domain": "nowhere.invalid"},
        ],
        target_personas=["CMO"],
    )
    assertion(s2["created"] == 1 and s2["skipped"] == 1,
              f"csv-2 summary -> {s2}", failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[8/9 pipeline run via PipelineRunner]")
    runner = PipelineRunner(repos, vtlog)
    run_id = runner.run_now(
        project_id=project_id, icp_id=icp_id, run_type="contact_discovery",
        config={"sources": [{
            "name": "csv-3",
            "records": [
                {"first_name": "Eve", "email": "eve@acme.com",
                 "job_title": "CMO", "company_id": acme["id"]},
                {"first_name": "Frank", "email": "frank@beta.io",
                 "job_title": "Head of CRM", "company_domain": "beta.io"},
                {"first_name": "Bad", "email": "bad@nope.com"},
            ],
        }]},
    )
    run = repos.pipeline_runs.get(run_id)
    assertion(run["status"] == "completed", f"run status -> {run['status']}", failures)
    assertion(run["total_created"] >= 1, f"total_created -> {run['total_created']}", failures)
    steps = repos.pipeline_run_steps.find({"pipeline_run_id": run_id})
    cd_step = next((s for s in steps if s["module_name"] == "ContactDiscoveryModule"), None)
    assertion(cd_step is not None and cd_step["output_count"] >= 1,
              f"ContactDiscoveryModule step -> {cd_step and cd_step['output_count']}",
              failures)

    # ─────────────────────────────────────────────────────────────
    print("\n[9/9 registry assertions]")
    rts = runner.registry.known_run_types()
    assertion("contact_discovery" in rts, "contact_discovery registered", failures)
    fp_modules = [m.__name__ for m in runner.registry.get("full_pipeline")]
    assertion(fp_modules[:3] == ["CompanyDiscoveryModule", "ContactDiscoveryModule", "DummyEchoModule"],
              f"full_pipeline first 3 -> {fp_modules}", failures)

    storage.close()
    print("\n" + ("=" * 50))
    if failures:
        print(f"FAIL — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — all assertions ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
