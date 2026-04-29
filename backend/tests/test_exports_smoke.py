"""Smoke test for File 19 — lead exports + CRM-ready delivery."""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api_shared import repos  # noqa: E402
from main import app  # noqa: E402
from services.export_service import (  # noqa: E402
    Destination, build_payload_for_lead, delivery_summary, get_default_destination,
    redeliver, run_export, set_default_destination,
)


def _seed() -> dict:
    pid = repos.projects.create({"name": "exp19", "slug": "exp19"})
    icp = repos.icps.create({
        "project_id": pid, "name": "ICP-A", "status": "active",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co = repos.companies.create({
        "project_id": pid, "name": "Acme19", "domain": "acme19.example",
        "industry": "saas", "country": "Germany", "employee_count": 90,
        "status": "qualified",
    })

    leads: list[int] = []
    msg_ids: list[int] = []
    for i, (fn, ln, tier, score) in enumerate([
        ("Alex", "Doe", "A", 0.95),
        ("Bea", "Smith", "B", 0.78),
        ("Cleo", "Lin", "A", 0.91),
    ]):
        ct = repos.contacts.create({
            "project_id": pid, "company_id": co,
            "first_name": fn, "last_name": ln, "full_name": f"{fn} {ln}",
            "email": f"{fn.lower()}@acme19.example", "job_title": "CTO", "status": "new",
        })
        lid = repos.lead_candidates.create({
            "project_id": pid, "icp_id": icp, "company_id": co, "contact_id": ct,
            "lead_status": "qualified", "priority_tier": tier, "final_score": score,
        })
        leads.append(lid)
        if i == 0:
            mid = repos.outreach_messages.create({
                "lead_id": lid, "channel": "email",
                "subject": "Hello Alex", "body": "Body for Alex." + " w" * 60,
                "status": "approved", "approved_at": "2026-01-01T00:00:00",
            })
            msg_ids.append(mid)

    # Experiment with declared winner; assign first lead to winner variant.
    exp_id = repos.outreach_experiments.create({
        "project_id": pid, "icp_id": icp, "name": "Exp1", "status": "completed",
        "primary_metric": "positive_reply_rate", "config": {},
    })
    var_a = repos.outreach_variants.create({
        "experiment_id": exp_id, "name": "control", "weight": 1.0,
        "is_control": 1, "params": {},
    })
    var_b = repos.outreach_variants.create({
        "experiment_id": exp_id, "name": "challenger", "weight": 1.0,
        "is_control": 0, "params": {},
    })
    repos.outreach_experiments.update(exp_id, {"winner_variant_id": var_b})
    repos.lead_variant_assignments.create({
        "lead_id": leads[0], "experiment_id": exp_id, "variant_id": var_b,
    })
    # Patch outreach_messages.variant_id for first message
    repos.outreach_messages.update(msg_ids[0], {"variant_id": var_b})

    return {
        "project_id": pid, "icp_id": icp, "company_id": co,
        "lead_ids": leads, "msg_id": msg_ids[0],
        "experiment_id": exp_id, "winner_variant_id": var_b,
    }


def test_payload_assembly(seed: dict) -> None:
    lead = repos.lead_candidates.get(seed["lead_ids"][0])
    payload = build_payload_for_lead(repos, lead)
    assert payload["lead"]["id"] == seed["lead_ids"][0]
    assert payload["company"]["domain"] == "acme19.example"
    assert payload["contact"]["first_name"] == "Alex"
    assert payload["icp"]["id"] == seed["icp_id"]
    assert payload["outreach_message"]["id"] == seed["msg_id"]
    assert payload["winning_variant"]["id"] == seed["winner_variant_id"]
    assert payload["is_winning_variant"] is True
    print("✓ payload assembly")


def test_run_export_csv_filesystem(seed: dict) -> None:
    res = run_export(
        repos,
        project_id=seed["project_id"],
        icp_id=seed["icp_id"],
        name="csv-all",
        destination="filesystem",
        format="csv",
        filters=None,
    )
    assert res["row_count"] == 3, res
    export = res["export"]
    assert export["status"] == "delivered"
    assert export["artifact_size_bytes"] and export["artifact_size_bytes"] > 0
    assert export["artifact_path"] and os.path.isfile(export["artifact_path"])
    text = Path(export["artifact_path"]).read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    assert len(rows) == 3
    assert "lead_id" in reader.fieldnames
    assert "outreach_subject" in reader.fieldnames
    assert "is_winning_variant" in reader.fieldnames
    # Row for first lead has winning variant
    win_row = next(r for r in rows if int(r["lead_id"]) == seed["lead_ids"][0])
    assert win_row["is_winning_variant"] == "1"
    assert win_row["variant_name"] == "challenger"
    print("✓ csv filesystem export")
    return export


def test_run_export_json_with_filters(seed: dict) -> None:
    res = run_export(
        repos,
        project_id=seed["project_id"],
        icp_id=seed["icp_id"],
        name="json-tierA",
        destination="filesystem",
        format="json",
        filters={"priority_tier": ["A"], "min_score": 0.9},
    )
    assert res["row_count"] == 2, res
    data = json.loads(Path(res["export"]["artifact_path"]).read_text())
    assert isinstance(data, list) and len(data) == 2
    tiers = {p["lead"]["priority_tier"] for p in data}
    assert tiers == {"A"}
    print("✓ json export with filters")


def test_destination_stubs(seed: dict) -> None:
    for dest in ("hubspot", "salesforce"):
        res = run_export(
            repos,
            project_id=seed["project_id"],
            name=f"{dest}-run",
            destination=dest,
            format="csv",
            filters={"priority_tier": ["A"]},
        )
        assert res["delivery"]["delivered"] is True
        assert res["delivery"]["simulated"] is True
        assert res["export"]["status"] == "delivered"
    print("✓ hubspot + salesforce stub destinations")


def test_pluggable_override(seed: dict) -> None:
    calls: list[dict] = []

    class Recorder:
        name = "filesystem"

        def deliver(self, export, items, artifact_path):
            calls.append({"export_id": export["id"], "n": len(items)})
            return {"destination": "filesystem", "delivered": True, "row_count": len(items),
                    "recorded": True}

    set_default_destination("filesystem", Recorder())
    try:
        res = run_export(
            repos,
            project_id=seed["project_id"],
            name="override",
            destination="filesystem",
        )
        assert res["delivery"].get("recorded") is True
        assert calls and calls[0]["n"] == 3
    finally:
        set_default_destination("filesystem", None)
    # confirm reset
    assert get_default_destination("filesystem").__class__.__name__ == "FilesystemDestination"
    print("✓ pluggable destination override + reset")


def test_pipeline_module(seed: dict) -> None:
    from api_shared import pipeline_runner
    run_id = pipeline_runner.run_now(
        run_type="export",
        project_id=seed["project_id"],
        icp_id=seed["icp_id"],
        config={"name": "via-pipeline", "format": "csv", "filters": {"min_score": 0.7}},
    )
    from api_shared import repos; summary = repos.pipeline_runs.get(run_id); assert summary["status"] == "completed", summary
    print("✓ ExportModule via pipeline_runner.run_now")


def test_api_routes(seed: dict) -> int:
    client = TestClient(app)

    # POST
    r = client.post("/exports", json={
        "project_id": seed["project_id"],
        "icp_id": seed["icp_id"],
        "name": "api-csv",
        "destination": "filesystem",
        "format": "csv",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    api_export_id = body["export"]["id"]
    assert body["row_count"] == 3

    # GET list
    r = client.get(f"/exports?project_id={seed['project_id']}")
    assert r.status_code == 200
    assert any(e["id"] == api_export_id for e in r.json()["data"])

    # GET detail
    r = client.get(f"/exports/{api_export_id}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["item_count"] == 3
    assert detail["summary"]["destination"] == "filesystem"

    # GET items
    r = client.get(f"/exports/{api_export_id}/items")
    assert r.status_code == 200
    assert r.json()["count"] == 3

    # GET download
    r = client.get(f"/exports/{api_export_id}/download")
    assert r.status_code == 200
    assert "lead_id" in r.text.splitlines()[0]

    # POST redeliver
    r = client.post(f"/exports/{api_export_id}/redeliver")
    assert r.status_code == 200
    assert r.json()["delivery"]["delivered"] is True

    # 400 invalid destination
    r = client.post("/exports", json={
        "project_id": seed["project_id"], "name": "bad", "destination": "mailchimp",
    })
    assert r.status_code == 400

    # 400 invalid format
    r = client.post("/exports", json={
        "project_id": seed["project_id"], "name": "bad", "format": "xml",
    })
    assert r.status_code == 400

    # 400 missing name
    r = client.post("/exports", json={"project_id": seed["project_id"]})
    assert r.status_code == 400

    # 404 missing export
    r = client.get("/exports/999999")
    assert r.status_code == 404
    r = client.get("/exports/999999/items")
    assert r.status_code == 404
    r = client.get("/exports/999999/download")
    assert r.status_code == 404
    r = client.post("/exports/999999/redeliver")
    assert r.status_code == 404

    # 404 unknown project on POST
    r = client.post("/exports", json={"project_id": 999999, "name": "x"})
    assert r.status_code == 404

    print("✓ API routes (6) + 400/404 validation")
    return api_export_id


def main() -> None:
    seed = _seed()
    test_payload_assembly(seed)
    test_run_export_csv_filesystem(seed)
    test_run_export_json_with_filters(seed)
    test_destination_stubs(seed)
    test_pluggable_override(seed)
    test_pipeline_module(seed)
    test_api_routes(seed)
    print("\nALL FILE 19 EXPORT SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
