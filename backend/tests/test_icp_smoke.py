"""Smoke test for ICP module. Runs against a temp DB. Prints PASS/FAIL.

Usage:
    python tests/test_icp_smoke.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT_DIR = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT_DIR)

from db.sqlite_storage import SQLiteStorage
from repositories import RepoRegistry
from services.icp_service import (
    ICPService, normalize_icp_payload, validate_icp_payload,
)
from setup_database import apply_migrations


def assertion(cond: bool, msg: str, failures: list[str]) -> None:
    print(f"  {'OK' if cond else 'FAIL'}  {msg}")
    if not cond:
        failures.append(msg)


def expect_value_error(fn, msg: str, failures: list[str]) -> None:
    try:
        fn()
    except ValueError:
        print(f"  OK    {msg}")
        return
    except Exception as e:
        print(f"  FAIL  {msg} (got {type(e).__name__}: {e})")
        failures.append(msg)
        return
    print(f"  FAIL  {msg} (no error raised)")
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
    svc = ICPService(repos)

    project_id = repos.projects.create({"name": "TestCo"})
    assertion(project_id > 0, f"project created id={project_id}", failures)

    print("\n[normalization]")
    norm = normalize_icp_payload({
        "name": "  ICP One  ",
        "target_industries": ["SaaS", "fintech", "saas", " SaaS "],
        "target_roles": ["CTO", "Head of Eng", "cto"],
        "target_geographies": "EU, US, eu",
        "target_seniorities": ["c_level", "vp"],
    }, is_create=True)
    assertion(norm["name"] == "ICP One", "name stripped", failures)
    assertion(norm["target_industries"] == ["saas", "fintech"],
              f"industries lowercased+deduped -> {norm['target_industries']}", failures)
    assertion(norm["target_roles"] == ["cto", "head of eng"],
              f"roles lowercased+deduped -> {norm['target_roles']}", failures)
    assertion(norm["target_geographies"] == ["eu", "us"],
              f"geographies parsed from CSV -> {norm['target_geographies']}", failures)
    assertion(norm["status"] == "draft", "default status=draft on create", failures)

    print("\n[validation]")
    expect_value_error(
        lambda: svc.create(project_id, {"name": "x", "target_industries": [], "target_roles": ["cto"]}),
        "rejects empty industries", failures,
    )
    expect_value_error(
        lambda: svc.create(project_id, {"name": "x", "target_industries": ["saas"], "target_roles": []}),
        "rejects empty roles", failures,
    )
    expect_value_error(
        lambda: svc.create(project_id, {
            "name": "x", "target_industries": ["saas"], "target_roles": ["cto"],
            "target_company_size_min": 500, "target_company_size_max": 100,
        }),
        "rejects min > max", failures,
    )
    expect_value_error(
        lambda: validate_icp_payload({"name": "", "target_industries": ["a"], "target_roles": ["b"]}),
        "rejects empty name", failures,
    )

    print("\n[create + filter]")
    icp_a = svc.create(project_id, {
        "name": "Alpha",
        "target_industries": ["SaaS", "Fintech"],
        "target_roles": ["CTO", "Head of Eng"],
        "target_geographies": ["EU"],
        "target_company_size_min": 50,
        "target_company_size_max": 500,
    })
    icp_b = svc.create(project_id, {
        "name": "Beta",
        "target_industries": ["edtech"],
        "target_roles": ["cmo"],
        "target_geographies": ["US"],
        "status": "active",
    })
    assertion(icp_a > 0 and icp_b > 0, f"created icp_a={icp_a} icp_b={icp_b}", failures)

    all_icps = repos.icps.find_for_project(project_id)
    assertion(len(all_icps) == 2, f"find_for_project all -> {len(all_icps)}", failures)

    drafts = repos.icps.find_for_project(project_id, status="draft")
    actives = repos.icps.find_for_project(project_id, status="active")
    assertion(len(drafts) == 1 and drafts[0]["id"] == icp_a,
              f"draft filter -> {[i['id'] for i in drafts]}", failures)
    assertion(len(actives) == 1 and actives[0]["id"] == icp_b,
              f"active filter -> {[i['id'] for i in actives]}", failures)

    print("\n[update]")
    svc.update(icp_a, {"name": "Alpha Renamed"})
    a_new = repos.icps.get(icp_a)
    assertion(a_new["name"] == "Alpha Renamed", "name updated", failures)
    assertion(a_new["target_industries"] == ["saas", "fintech"],
              "industries preserved on partial update", failures)

    print("\n[lifecycle]")
    repos.icps.activate(icp_a)
    assertion(repos.icps.get(icp_a)["status"] == "active", "activate -> active", failures)
    repos.icps.archive(icp_a)
    assertion(repos.icps.get(icp_a)["status"] == "archived", "archive -> archived", failures)

    print("\n[clone]")
    cloned_id = repos.icps.clone(icp_b, "Beta (copy)")
    cloned = repos.icps.get(cloned_id)
    assertion(cloned_id != icp_b, f"clone has new id {cloned_id}", failures)
    assertion(cloned["status"] == "draft", "clone is draft", failures)
    assertion(cloned["name"] == "Beta (copy)", "clone name preserved", failures)
    assertion(cloned["target_industries"] == ["edtech"],
              "clone industries match source", failures)

    print("\n[summary]")
    summ = svc.summary_for_dashboard(icp_a)
    expected_zero = ("companies_targeted", "contacts_targeted", "leads_total",
                     "leads_ready", "drafts_total", "drafts_pending", "signals_total")
    for k in expected_zero:
        assertion(summ.get(k) == 0, f"summary {k}=0", failures)

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
