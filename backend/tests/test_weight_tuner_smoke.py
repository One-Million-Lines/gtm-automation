"""File 21 — Scoring weight auto-tuning smoke test."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from api_shared import pipeline_runner, repos
from main import app
from services.feedback_service import record_feedback
from services.weight_tuner_service import (
    HeuristicWeightTuner, approve_revision, baseline_weights_for_icp, diff_weights,
    get_default_weight_tuner, propose_revision, reject_revision, revision_summary,
    rollback_to, run_tuning_for_project, set_default_weight_tuner,
)


def seed() -> dict:
    pid = repos.projects.create({"name": "f21", "slug": "f21"})
    icp = repos.icps.create({
        "project_id": pid, "name": "ICP21", "status": "active",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co = repos.companies.create({
        "project_id": pid, "name": "AcmeF21", "domain": "acmef21.example",
        "industry": "saas", "status": "discovered",
    })
    leads: list[int] = []
    for i in range(3):
        ct = repos.contacts.create({
            "project_id": pid, "company_id": co,
            "first_name": f"P{i}", "last_name": "X",
            "full_name": f"P{i} X", "job_title": "CTO",
            "email": f"p{i}@acmef21.example", "status": "new",
        })
        lid = repos.lead_candidates.create({
            "project_id": pid, "icp_id": icp, "company_id": co, "contact_id": ct,
            "lead_status": "scored", "priority_tier": "A", "final_score": 0.8,
            "lifecycle_stage": "new",
        })
        msg = repos.outreach_messages.create({
            "project_id": pid, "lead_id": lid, "channel": "email",
            "subject": f"hi{i}", "body": "Hello there " + " ".join(["w"] * 60),
            "status": "sent",
        })
        leads.append(lid)
        # Record + apply mixed signals.
        record_feedback(
            repos, project_id=pid, kind="lead_qualified", source="human",
            lead_id=lid, icp_id=icp, outreach_message_id=msg, weight=1.0,
            auto_apply=True,
        )
    # Add positive: won + meeting_booked
    record_feedback(
        repos, project_id=pid, kind="won", source="human",
        lead_id=leads[0], icp_id=icp, weight=1.0, auto_apply=True,
    )
    record_feedback(
        repos, project_id=pid, kind="meeting_booked", source="human",
        lead_id=leads[1], icp_id=icp, weight=1.0, auto_apply=True,
    )
    # Add negative: disqualified + lost
    record_feedback(
        repos, project_id=pid, kind="lead_disqualified", source="human",
        lead_id=leads[2], icp_id=icp, weight=1.0, auto_apply=True,
    )
    record_feedback(
        repos, project_id=pid, kind="lost", source="human",
        lead_id=leads[2], icp_id=icp, weight=1.0, auto_apply=True,
    )
    return {"project_id": pid, "icp_id": icp, "leads": leads}


def test_propose(s: dict) -> dict:
    res = propose_revision(
        repos, icp_id=s["icp_id"], project_id=s["project_id"],
        notes="initial proposal", created_by="smoke",
    )
    rev = res["revision"]
    assert rev["status"] == "proposed", rev
    assert rev["source"] == "auto_tune"
    stats = res["stats"]
    assert stats["dataset_size"] >= 6, stats
    assert stats["positive_n"] >= 4
    assert stats["negative_n"] >= 2
    assert stats["confidence"] > 0
    assert repos.scoring_weight_revisions.get_active_for_icp(s["icp_id"]) is None
    print(f"✓ propose (dataset={stats['dataset_size']} conf={stats['confidence']:.3f})")
    return res


def test_diff_signal_positive(res: dict) -> None:
    proposed = res["proposed"]
    assert "fit" in proposed and "signal" in proposed
    fit_sum = sum(proposed["fit"].values())
    assert abs(fit_sum - 1.0) < 1e-6, fit_sum
    diff = res["diff"]
    assert any(r["namespace"] == "signal" for r in diff)
    print("✓ diff (fit renormalised, signal present)")


def test_approve(rev_id: int) -> dict:
    res = approve_revision(repos, rev_id)
    assert res["revision"]["status"] == "active"
    assert res["revision"]["activated_at"] is not None
    assert res["previous_active_id"] is None
    print("✓ approve (first active)")
    return res


def test_propose_again_no_active_mutation(s: dict, first_active_id: int) -> dict:
    res = propose_revision(
        repos, icp_id=s["icp_id"], project_id=s["project_id"],
        notes="second proposal", created_by="smoke",
    )
    assert res["revision"]["status"] == "proposed"
    active = repos.scoring_weight_revisions.get_active_for_icp(s["icp_id"])
    assert active is not None and active["id"] == first_active_id
    print("✓ propose-again (active untouched)")
    return res


def test_approve_archives_prior(second_rev_id: int, first_active_id: int) -> None:
    res = approve_revision(repos, second_rev_id)
    assert res["previous_active_id"] == first_active_id
    prior = repos.scoring_weight_revisions.get(first_active_id)
    assert prior["status"] == "archived"
    assert prior["archived_at"] is not None
    print("✓ approve-archives-prior")


def test_rollback(s: dict, first_active_id: int) -> None:
    res = rollback_to(
        repos, first_active_id, created_by="smoke", notes="rollback test",
    )
    new_rev = res["revision"]
    assert new_rev["source"] == "rollback"
    assert new_rev["status"] == "active"
    src = repos.scoring_weight_revisions.get(first_active_id)
    assert new_rev["proposed_weights"] == src["proposed_weights"]
    print(f"✓ rollback (new id={new_rev['id']} from={first_active_id})")


def test_reject(s: dict) -> None:
    res = propose_revision(
        repos, icp_id=s["icp_id"], project_id=s["project_id"],
        notes="to reject", created_by="smoke",
    )
    rid = res["revision"]["id"]
    rj = reject_revision(repos, rid, reason="not aligned")
    assert rj["revision"]["status"] == "rejected"
    # Active revision cannot be rejected.
    active = repos.scoring_weight_revisions.get_active_for_icp(s["icp_id"])
    try:
        reject_revision(repos, active["id"])
    except ValueError as exc:
        assert "cannot reject" in str(exc).lower(), exc
    else:
        raise AssertionError("expected ValueError for rejecting active")
    print("✓ reject (and active-cannot-be-rejected)")


def test_run_tuning_auto_promote(s: dict) -> None:
    res = run_tuning_for_project(
        repos, project_id=s["project_id"], icp_ids=[s["icp_id"]],
        auto_promote=True, confidence_threshold=0.0,
        notes="auto run", created_by="smoke",
    )
    assert res["proposed_count"] == 1
    assert res["promoted_count"] == 1
    assert res["skipped_count"] == 0
    print("✓ run_tuning auto_promote")


def test_pipeline_module(s: dict) -> None:
    run_id = pipeline_runner.run_now(
        run_type="weight_tuning",
        project_id=s["project_id"],
        icp_id=s["icp_id"],
        config={"auto_promote": False, "notes": "pipeline-run"},
    )
    summary = repos.pipeline_runs.get(run_id)
    assert summary["status"] == "completed", summary
    print("✓ pipeline weight_tuning module")


def test_pluggable_adapter(s: dict) -> None:
    calls: list[dict] = []

    class Recorder:
        name = "recorder"

        def tune(self, *, baseline, events):
            calls.append({"baseline": baseline, "n": len(events)})
            return {
                "proposed_weights": baseline,
                "contributing_event_ids": [int(e["id"]) for e in events],
                "stats": {"dataset_size": len(events), "positive_n": 0,
                          "negative_n": 0, "mean_weight_shift": 0.0,
                          "max_shift": 0.0, "confidence": 0.42,
                          "per_feature_shift": {}},
            }

    set_default_weight_tuner(Recorder())
    try:
        propose_revision(
            repos, icp_id=s["icp_id"], project_id=s["project_id"],
            notes="recorder", created_by="smoke",
        )
        assert len(calls) == 1
    finally:
        set_default_weight_tuner(None)
    assert isinstance(get_default_weight_tuner(), HeuristicWeightTuner)
    print("✓ pluggable adapter")


def test_api_routes(s: dict) -> None:
    client = TestClient(app)
    r = client.get(f"/icps/{s['icp_id']}/scoring/weights")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "active" in data and "history" in data

    r = client.get(f"/icps/{s['icp_id']}/scoring/revisions")
    assert r.status_code == 200
    assert r.json()["count"] >= 1

    # propose missing project_id → 400
    r = client.post(f"/icps/{s['icp_id']}/scoring/propose", json={})
    assert r.status_code == 400

    r = client.post(
        f"/icps/{s['icp_id']}/scoring/propose",
        json={"project_id": s["project_id"], "created_by": "api"},
    )
    assert r.status_code == 200, r.text
    new_rev_id = r.json()["revision"]["id"]

    r = client.get(f"/scoring/revisions/{new_rev_id}")
    assert r.status_code == 200
    assert "diff" in r.json()

    r = client.post(f"/scoring/revisions/{new_rev_id}/reject", json={"reason": "no"})
    assert r.status_code == 200
    assert r.json()["revision"]["status"] == "rejected"

    # missing icp / revision → 404
    assert client.get("/icps/999999/scoring/weights").status_code == 404
    assert client.get("/scoring/revisions/999999").status_code == 404

    # tuning run endpoint
    r = client.post(
        "/scoring/tuning/run",
        json={"project_id": s["project_id"], "icp_ids": [s["icp_id"]],
              "auto_promote": False},
    )
    assert r.status_code == 200, r.text
    print("✓ api routes")


def main() -> None:
    s = seed()
    res = test_propose(s)
    test_diff_signal_positive(res)
    test_approve(res["revision"]["id"])
    first_active_id = res["revision"]["id"]
    res2 = test_propose_again_no_active_mutation(s, first_active_id)
    test_approve_archives_prior(res2["revision"]["id"], first_active_id)
    test_rollback(s, first_active_id)
    test_reject(s)
    test_run_tuning_auto_promote(s)
    test_pipeline_module(s)
    test_pluggable_adapter(s)
    test_api_routes(s)
    print("\nALL FILE 21 SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
