"""Smoke test for File 08 — suppression module."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import repos
from services.suppression_service import (
    apply_suppression_to_leads, ingest_records, normalize_record, normalize_value,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    print("\n[normalize_value]")
    assertion(normalize_value("domain", "https://www.SPAM.com/path") == "spam.com",
              "domain normalized", failures)
    assertion(normalize_value("email", " A@B.IO ") == "a@b.io", "email normalized", failures)
    assertion(normalize_value("email", "broken") is None, "email invalid -> None", failures)
    assertion(normalize_value("linkedin_url", "https://linkedin.com/in/X/") == "https://linkedin.com/in/x",
              "linkedin normalized", failures)
    assertion(normalize_value("company_name", " Acme Inc ") == "acme inc", "name normalized", failures)
    assertion(normalize_value("nope", "x") is None, "invalid type -> None", failures)

    print("\n[normalize_record]")
    assertion(normalize_record({"suppression_type": "domain", "value": "x.com"})["value"] == "x.com",
              "valid record passes", failures)
    assertion(normalize_record({"suppression_type": "domain", "value": ""}) is None,
              "empty value rejected", failures)

    # ---------- setup project + ICP + companies + contacts + leads ----------
    project_id = repos.projects.create({"name": "smoke08"})
    icp_id = repos.icps.create({
        "project_id": project_id, "name": "ICP08", "status": "active",
        "target_industries": ["saas"], "target_personas": ["CMO"],
        "target_roles": ["cto"],
    })
    c_acme = repos.companies.upsert_by_domain({"domain": "acme.com", "name": "Acme"})
    c_beta = repos.companies.upsert_by_domain({"domain": "beta.io", "name": "Beta"})
    c_gamma = repos.companies.upsert_by_domain({"domain": "gamma.co", "name": "GammaCorp"})

    ct_jane = repos.contacts.create({
        "company_id": c_acme, "full_name": "Jane Doe", "email": "jane@acme.com",
    })
    ct_bob = repos.contacts.create({
        "company_id": c_beta, "full_name": "Bob", "email": "bob@beta.io",
        "linkedin_url": "https://linkedin.com/in/bob",
    })
    ct_amy = repos.contacts.create({
        "company_id": c_gamma, "full_name": "Amy",
    })

    repos.lead_candidates.create({
        "project_id": project_id, "icp_id": icp_id, "company_id": c_acme,
        "contact_id": ct_jane, "lead_status": "new",
    })
    repos.lead_candidates.create({
        "project_id": project_id, "icp_id": icp_id, "company_id": c_beta,
        "contact_id": ct_bob, "lead_status": "new",
    })
    repos.lead_candidates.create({
        "project_id": project_id, "icp_id": icp_id, "company_id": c_gamma,
        "contact_id": ct_amy, "lead_status": "new",
    })

    # ---------- ingest_records ----------
    print("\n[ingest_records]")
    res = ingest_records(repos, [
        {"suppression_type": "domain", "value": "https://www.acme.com/"},
        {"suppression_type": "email", "value": "BOB@beta.io"},
        {"suppression_type": "company_name", "value": "GammaCorp"},
        {"suppression_type": "domain", "value": ""},  # invalid
        {"suppression_type": "bogus", "value": "x"},   # invalid
    ])
    assertion(res["created"] == 3, f"created=3 (got {res['created']})", failures)
    assertion(res["invalid"] == 2, f"invalid=2 (got {res['invalid']})", failures)
    assertion(repos.suppression.is_suppressed("domain", "acme.com"),
              "acme.com domain suppressed", failures)
    assertion(repos.suppression.is_suppressed("email", "bob@beta.io"),
              "bob@beta.io email suppressed", failures)

    # idempotent
    res2 = ingest_records(repos, [
        {"suppression_type": "domain", "value": "acme.com"},
    ])
    assertion(res2["existing"] == 1 and res2["created"] == 0, "idempotent re-add", failures)

    # ---------- apply (dry_run) ----------
    print("\n[apply dry_run]")
    dry = apply_suppression_to_leads(repos, project_id=project_id, dry_run=True)
    assertion(dry["scanned"] == 3, f"scanned 3 (got {dry['scanned']})", failures)
    assertion(dry["suppressed"] == 3, f"suppressed 3 (got {dry['suppressed']})", failures)
    # verify nothing changed yet
    leads_now = repos.lead_candidates.find({"project_id": project_id})
    assertion(all(l["lead_status"] == "new" for l in leads_now),
              "dry_run did NOT mutate leads", failures)

    # ---------- apply (real) ----------
    print("\n[apply real]")
    real = apply_suppression_to_leads(repos, project_id=project_id, dry_run=False)
    assertion(real["suppressed"] == 3, f"3 suppressed (got {real['suppressed']})", failures)
    assertion(real["by_reason"].get("domain", 0) == 1, "1 by domain", failures)
    assertion(real["by_reason"].get("email", 0) == 1, "1 by email", failures)
    assertion(real["by_reason"].get("company_name", 0) == 1, "1 by name", failures)

    leads_after = repos.lead_candidates.find({"project_id": project_id})
    assertion(all(l["lead_status"] == "suppressed" for l in leads_after),
              "all leads now suppressed", failures)
    assertion(all((l.get("rejection_reason") or "").startswith("suppressed:") for l in leads_after),
              "rejection_reason set", failures)

    # ---------- re-apply: no double suppression ----------
    re2 = apply_suppression_to_leads(repos, project_id=project_id)
    assertion(re2["scanned"] == 0 and re2["suppressed"] == 0,
              "re-apply skips already-suppressed", failures)

    # ---------- pipeline module ----------
    print("\n[pipeline run]")
    from api_shared import pipeline_runner
    # Add a fresh project to avoid status filter exclusion
    p2 = repos.projects.create({"name": "smoke08-pipe"})
    icp2 = repos.icps.create({
        "project_id": p2, "name": "ICP08p", "status": "active",
        "target_industries": ["saas"], "target_personas": ["CMO"], "target_roles": ["cto"],
    })
    cx = repos.companies.upsert_by_domain({"domain": "acme.com", "name": "Acme"})
    repos.lead_candidates.create({
        "project_id": p2, "icp_id": icp2, "company_id": cx,
        "contact_id": None, "lead_status": "new",
    })
    run_id = pipeline_runner.run_now(
        project_id=p2, icp_id=icp2, run_type="suppression",
        config={"records": [{"suppression_type": "domain", "value": "acme.com"}],
                "scope": "project"},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    assertion(detail["run"]["status"] == "completed",
              f"pipeline status completed (got {detail['run']['status']})", failures)
    p2_leads = repos.lead_candidates.find({"project_id": p2})
    assertion(p2_leads[0]["lead_status"] == "suppressed", "pipeline suppressed the new lead", failures)

    print("\n--- summary ---")
    if failures:
        print(f"FAILED: {len(failures)} assertion(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
