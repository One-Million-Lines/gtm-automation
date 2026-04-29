"""Smoke test for File 10 — contact enrichment (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.contact_enrichment_service import (
    enrich_contact, enrich_contacts_batch, import_enriched_contacts,
    parse_enriched_csv,
)
from services.email_validator import (
    EMAIL_SYNTAX_RE, FakeEmailValidator, classify, normalize_email,
    set_default_validator, validate_email,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # --- 1. syntax + normalize -------------------------------------------------
    print("\n[syntax]")
    assertion(EMAIL_SYNTAX_RE.match("a.b+x@example.co.uk") is not None, "valid syntax", failures)
    assertion(EMAIL_SYNTAX_RE.match("bad@@x.com") is None, "double-@ rejected", failures)
    assertion(normalize_email(" Foo@Bar.COM ") == "foo@bar.com", "normalize lowercases+trims", failures)

    # --- 2. classify ----------------------------------------------------------
    print("\n[classify]")
    s, c, _ = classify(syntax_ok=False, has_mx=None, is_disposable=False, is_role=False, is_free=False, is_catch_all=None)
    assertion(s == "invalid", "bad syntax -> invalid", failures)
    s, c, _ = classify(syntax_ok=True, has_mx=False, is_disposable=False, is_role=False, is_free=False, is_catch_all=None)
    assertion(s == "invalid", "no MX -> invalid", failures)
    s, c, _ = classify(syntax_ok=True, has_mx=True, is_disposable=True, is_role=False, is_free=False, is_catch_all=None)
    assertion(s == "disposable", "disposable -> disposable", failures)
    s, c, _ = classify(syntax_ok=True, has_mx=True, is_disposable=False, is_role=True, is_free=False, is_catch_all=None)
    assertion(s == "role", "role local -> role", failures)
    s, c, _ = classify(syntax_ok=True, has_mx=True, is_disposable=False, is_role=False, is_free=False, is_catch_all=True)
    assertion(s == "risky", "catch_all -> risky", failures)
    s, c, _ = classify(syntax_ok=True, has_mx=True, is_disposable=False, is_role=False, is_free=False, is_catch_all=None)
    assertion(s == "valid" and c >= 0.9, "mx ok corp -> valid 0.9", failures)
    s, c, _ = classify(syntax_ok=True, has_mx=True, is_disposable=False, is_role=False, is_free=True, is_catch_all=None)
    assertion(s == "valid" and 0.7 <= c < 0.9, "mx ok free -> valid 0.8", failures)

    # --- 3. FakeEmailValidator + typo + disposable + role + catch_all ---------
    print("\n[FakeEmailValidator]")
    fv = FakeEmailValidator(
        domains_with_mx={"acme.com", "beta.io", "gamma.io"},
        domains_without_mx={"nodomain.test"},
        catch_all_domains={"catchall.io"},
    )
    set_default_validator(fv)

    r = validate_email("Jane.Doe@ACME.com")
    assertion(r.status == "valid" and r.domain == "acme.com" and r.normalized == "jane.doe@acme.com",
              f"corp valid {r.status}/{r.domain}", failures)

    r = validate_email("info@acme.com")
    assertion(r.status == "role" and r.is_role, "role local detected", failures)

    r = validate_email("foo@mailinator.com")
    assertion(r.status == "disposable", "disposable detected", failures)

    r = validate_email("foo@nodomain.test")
    assertion(r.status == "invalid" and r.has_mx is False, "no-MX -> invalid", failures)

    r = validate_email("foo@catchall.io")
    assertion(r.status == "risky" and r.is_catch_all, "catch_all -> risky", failures)

    r = validate_email("alex@gmial.com")
    assertion(r.typo_corrected == "gmial.com" and r.domain == "gmail.com" and r.status == "valid",
              "typo gmial.com -> gmail.com", failures)

    r = validate_email("not an email")
    assertion(r.status == "invalid" and r.syntax_ok is False, "bad syntax -> invalid", failures)

    r = validate_email("alex@unknown-corp.io")
    assertion(r.status == "unverified", "unknown corp domain -> unverified", failures)

    # --- 4. CSV parsing -------------------------------------------------------
    print("\n[parse_enriched_csv]")
    csv_text = "email,first_name,last_name,job_title,company_domain\n" \
               "alex@acme.com,Alex,Doe,Head of Marketing,acme.com\n" \
               ",,, , \n" \
               "info@beta.io,,,, beta.io \n"
    rows = parse_enriched_csv(csv_text)
    assertion(len(rows) == 2, f"2 valid rows -> {len(rows)}", failures)
    assertion(rows[0]["email"] == "alex@acme.com", "row0 email", failures)
    assertion(rows[1]["email"] == "info@beta.io", "row1 email", failures)

    # --- 5. End-to-end DB scenarios ------------------------------------------
    print("\n[db scenario setup]")
    # Reset DB state (in-memory repos already created via api_shared at import).
    # We assume the DB is freshly-initialized by the test runner.
    pid = repos.projects.create({"name": "proj_ce"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP", "status": "active",
        "target_industries": ["saas"], "target_roles": ["cto"],
        "target_personas": ["head of marketing"],
    })
    acme_id = repos.companies.create({"domain": "acme.com", "name": "Acme", "project_id": pid})
    beta_id = repos.companies.create({"domain": "beta.io", "name": "Beta", "project_id": pid})

    # Pre-create a contact with a typoed email
    cid_typo = repos.contacts.create({
        "company_id": acme_id, "email": "alex@gmial.com",
        "first_name": "Alex", "job_title": "Head of Marketing", "status": "new",
    })
    # Wire to lead_candidates so it shows up in project-scoped selection.
    repos.lead_candidates.upsert_full(
        icp_id=icp_id, company_id=acme_id, contact_id=cid_typo,
        data={"project_id": pid, "lead_status": "new"},
    )

    print("\n[enrich_contact single]")
    r = enrich_contact(repos, contact_id=cid_typo)
    assertion(r["ok"] is True, f"ok -> {r['ok']}", failures)
    assertion(r["status"] == "valid", f"status valid -> {r['status']}", failures)
    assertion(r["updates"].get("email") == "alex@gmail.com", "typo fixed in contact row", failures)
    assertion(r["updates"].get("status") == "enriched", "contact status -> enriched", failures)
    assertion(r["updates"].get("normalized_role") == "marketing_lead", "normalized_role filled", failures)
    assertion(r.get("enrichment_id") is not None, "snapshot persisted", failures)
    contact_after = repos.contacts.get(cid_typo)
    assertion(contact_after["email"] == "alex@gmail.com", "DB email rewritten", failures)
    assertion(contact_after["email_status"] == "valid", "DB email_status=valid", failures)

    print("\n[enrich_contact - missing email]")
    cid_no_email = repos.contacts.create({"company_id": acme_id, "full_name": "Anon", "status": "new"})
    r = enrich_contact(repos, contact_id=cid_no_email)
    assertion(r.get("skipped") and r.get("error") == "contact_missing_email",
              "missing email skipped cleanly", failures)

    print("\n[enrich_contact - invalid -> persists snapshot]")
    cid_bad = repos.contacts.create({"company_id": acme_id, "email": "x@nodomain.test", "status": "new"})
    repos.lead_candidates.upsert_full(
        icp_id=icp_id, company_id=acme_id, contact_id=cid_bad,
        data={"project_id": pid, "lead_status": "new"},
    )
    r = enrich_contact(repos, contact_id=cid_bad)
    assertion(r["status"] == "invalid", f"invalid status -> {r['status']}", failures)
    assertion(r.get("enrichment_id") is not None, "snapshot persisted even on invalid", failures)

    print("\n[enrich_contacts_batch only_missing]")
    res = enrich_contacts_batch(repos, project_id=pid, only_missing=True, limit=50)
    assertion(res["scanned"] >= 2, f"scanned -> {res['scanned']}", failures)
    assertion(res["skipped"] >= 2, "previously-enriched skipped", failures)

    print("\n[dry_run no-write]")
    cid_fresh = repos.contacts.create({"company_id": beta_id, "email": "ceo@beta.io", "status": "new"})
    repos.lead_candidates.upsert_full(
        icp_id=icp_id, company_id=beta_id, contact_id=cid_fresh,
        data={"project_id": pid, "lead_status": "new"},
    )
    before = repos.contact_enrichment.count({"contact_id": cid_fresh})
    r = enrich_contact(repos, contact_id=cid_fresh, dry_run=True)
    after = repos.contact_enrichment.count({"contact_id": cid_fresh})
    assertion(before == after == 0, "dry_run did not write", failures)
    assertion(r["status"] == "valid", "dry_run returns status anyway", failures)

    print("\n[import_enriched_contacts]")
    csv_text = (
        "email,first_name,last_name,job_title,company_domain\n"
        "newbie@gamma.io,New,Bie,Head of Growth,gamma.io\n"
        "info@beta.io,Generic,Mailbox,Sales,beta.io\n"
        "broken@gmial.com,Typo,User,CMO,acme.com\n"
        ",,,,acme.com\n"
    )
    # Need a gamma company.
    repos.companies.upsert_by_domain({"domain": "gamma.io", "name": "Gamma"})
    rows = parse_enriched_csv(csv_text)
    summary = import_enriched_contacts(
        repos, project_id=pid, icp_id=icp_id, records=rows,
        target_personas=["Head of Growth"],
    )
    assertion(summary["input"] == 4, f"input=4 -> {summary['input']}", failures)
    assertion(summary["created"] >= 1, f"created>=1 -> {summary['created']}", failures)
    assertion(summary["enriched"] >= 1, f"enriched>=1 -> {summary['enriched']}", failures)
    assertion(summary["skipped"] >= 1, f"skipped (empty row) >=1 -> {summary['skipped']}", failures)
    # Verify suppression re-applied summary block exists.
    assertion("suppression_reapplied" in summary, "suppression_reapplied present", failures)

    print("\n[pipeline run_type=contact_enrichment]")
    # Reset only_missing skip by adding a new contact.
    cid_pipe = repos.contacts.create({"company_id": acme_id, "email": "delta@acme.com", "status": "new"})
    repos.lead_candidates.upsert_full(
        icp_id=icp_id, company_id=acme_id, contact_id=cid_pipe,
        data={"project_id": pid, "lead_status": "new"},
    )
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id,
        run_type="contact_enrichment", config={"only_missing": True, "limit": 100},
    )
    detail = pipeline_runner.get_run_detail(int(run_id))
    assertion(detail["run"]["status"] == "completed",
              f"run completed -> {detail['run']['status']}", failures)
    after_pipe = repos.contacts.get(cid_pipe)
    assertion(after_pipe["email_status"] in ("unverified", "valid", "risky"),
              f"new contact got status -> {after_pipe['email_status']}", failures)

    print("\n========")
    if failures:
        print(f"FAIL — {len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — 0 failures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
