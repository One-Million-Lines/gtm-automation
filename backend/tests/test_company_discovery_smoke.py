"""Smoke test for company discovery. Temp DB. PASS/FAIL.

Usage:
    python tests/test_company_discovery_smoke.py
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
from services.company_discovery_service import (
    ingest_company_record, ingest_records, merge_company_payload, normalize_domain,
)
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
    vtlog = initLog("company_discovery_smoke")

    print("\n[normalize_domain]")
    cases = [
        ("https://www.example.com/pages/about", "example.com"),
        ("http://example.com", "example.com"),
        ("WWW.Example.CO.UK", "example.co.uk"),
        ("https://shop.example.com:8080/path?x=1", "shop.example.com"),
        ("not a domain", None),
        ("", None),
        (None, None),
        ("foo@bar.com", "bar.com"),
    ]
    for inp, want in cases:
        got = normalize_domain(inp)
        assertion(got == want, f"normalize_domain({inp!r}) -> {got!r} (want {want!r})", failures)

    print("\n[merge_company_payload]")
    merged = merge_company_payload(
        {"name": "Acme", "industry": "saas", "tech_stack": ["React"], "city": "Paris"},
        {"name": "", "industry": None, "tech_stack": ["TypeScript", "react"], "city": "Berlin"},
    )
    assertion(merged["name"] == "Acme", "keeps existing name when new is empty", failures)
    assertion(merged["industry"] == "saas", "keeps existing industry when new is None", failures)
    assertion(merged["city"] == "Berlin", "overwrites with non-empty new city", failures)
    assertion(set(merged["tech_stack"]) == {"React", "TypeScript"},
              f"tech_stack union (case-insens) -> {merged['tech_stack']}", failures)

    project_id = repos.projects.create({"name": "P"})
    icp_id = repos.icps.create({
        "project_id": project_id, "name": "ICP",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })

    print("\n[ingest two records]")
    rec_a = {"name": "Acme", "domain": "https://www.acme.com/about", "industry": "SaaS"}
    rec_b = {"name": "Beta", "website_url": "https://beta.io"}
    r_a = ingest_company_record(repos, project_id=project_id, icp_id=icp_id,
                                source_name="manual", raw=rec_a)
    r_b = ingest_company_record(repos, project_id=project_id, icp_id=icp_id,
                                source_name="manual", raw=rec_b)
    assertion(r_a["action"] == "created", f"a created -> {r_a}", failures)
    assertion(r_b["action"] == "created", f"b created -> {r_b}", failures)
    assertion(repos.companies.count({}) == 2, "2 companies", failures)
    assertion(repos.lead_candidates.count({"icp_id": icp_id}) == 2,
              "2 lead_candidates linked to ICP", failures)

    acme = repos.companies.find_one({"domain": "acme.com"})
    assertion(acme is not None and acme["domain"] == "acme.com",
              f"acme.com normalized -> {acme and acme['domain']}", failures)

    print("\n[re-ingest same domain]")
    r_a2 = ingest_company_record(repos, project_id=project_id, icp_id=icp_id,
                                 source_name="manual", raw=rec_a)
    assertion(r_a2["action"] == "updated", f"re-ingest -> {r_a2}", failures)
    assertion(repos.companies.count({}) == 2, "still 2 companies", failures)
    # second source row recorded
    sources = repos.company_sources.find({"company_id": r_a["company_id"]})
    assertion(len(sources) == 2, f"2 source rows for acme -> {len(sources)}", failures)

    print("\n[merge keeps name when new is empty]")
    ingest_company_record(
        repos, project_id=project_id, icp_id=icp_id, source_name="manual",
        raw={"domain": "acme.com", "name": "", "city": "NYC"},
    )
    a2 = repos.companies.find_one({"domain": "acme.com"})
    assertion(a2["name"] == "Acme", f"name preserved -> {a2['name']}", failures)
    assertion(a2["city"] == "NYC", f"city updated -> {a2['city']}", failures)

    print("\n[skip on missing domain + website]")
    r_skip = ingest_company_record(repos, project_id=project_id, icp_id=icp_id,
                                   source_name="manual", raw={"name": "NoDomain"})
    assertion(r_skip["action"] == "skipped", f"skipped -> {r_skip}", failures)
    assertion("missing" in (r_skip.get("reason") or ""), f"skip reason -> {r_skip['reason']}", failures)

    print("\n[ingest_records summary: 3 records, 1 missing domain]")
    summary = ingest_records(
        repos, project_id=project_id, icp_id=icp_id, source_name="csv-1",
        records=[
            {"name": "Gamma", "domain": "gamma.io"},
            {"name": "Delta", "website_url": "https://delta.com"},
            {"name": "broken"},
        ],
    )
    assertion(summary["created"] == 2 and summary["updated"] == 0 and summary["skipped"] == 1,
              f"summary -> {summary}", failures)

    print("\n[pipeline run via PipelineRunner]")
    runner = PipelineRunner(repos, vtlog)
    run_id = runner.run_now(
        project_id=project_id, icp_id=icp_id, run_type="company_discovery",
        config={"sources": [{
            "name": "manual",
            "records": [
                {"name": "Epsilon", "domain": "epsilon.com"},
                {"name": "Zeta", "website_url": "https://zeta.io"},
                {"name": "broken-no-dom"},
            ],
        }]},
    )
    run = repos.pipeline_runs.get(run_id)
    assertion(run["status"] == "completed", f"run status -> {run['status']}", failures)
    assertion(run["total_created"] == 2, f"run.total_created -> {run['total_created']}", failures)
    assertion(run["total_processed"] == 3, f"run.total_processed -> {run['total_processed']}", failures)
    steps = repos.pipeline_run_steps.find({"pipeline_run_id": run_id})
    cd_step = next((s for s in steps if s["module_name"] == "CompanyDiscoveryModule"), None)
    assertion(cd_step is not None and cd_step["output_count"] == 2,
              f"CompanyDiscoveryModule step output_count -> {cd_step and cd_step['output_count']}",
              failures)

    print("\n[run_types include company_discovery + full_pipeline]")
    rts = runner.registry.known_run_types()
    assertion("company_discovery" in rts, "company_discovery registered", failures)
    fp_modules = [m.__name__ for m in runner.registry.get("full_pipeline")]
    assertion(fp_modules and fp_modules[0] == "CompanyDiscoveryModule",
              f"full_pipeline first -> {fp_modules}", failures)

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
