"""File 20 — Feedback ingestion + lifecycle smoke test."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from api_shared import pipeline_runner, repos
from main import app
from services.feedback_service import (
    FakeLifecycleSyncAdapter, LIFECYCLE_STAGES,
    apply_unapplied_feedback, feedback_summary,
    get_default_lifecycle_sync_adapter, ingest_export_feedback, ingest_reply_feedback,
    record_feedback, run_ingestion, set_default_lifecycle_sync_adapter,
    transition_lead,
)


def seed() -> dict:
    pid = repos.projects.create({"name": "f20", "slug": "f20"})
    icp = repos.icps.create({
        "project_id": pid, "name": "ICP", "status": "active",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co = repos.companies.create({
        "project_id": pid, "name": "AcmeF20", "domain": "acmef20.example",
        "industry": "saas", "status": "discovered",
    })
    ct1 = repos.contacts.create({
        "project_id": pid, "company_id": co, "first_name": "L", "last_name": "X",
        "full_name": "L X", "job_title": "CTO", "email": "l@acmef20.example",
        "status": "new",
    })
    ct2 = repos.contacts.create({
        "project_id": pid, "company_id": co, "first_name": "M", "last_name": "Y",
        "full_name": "M Y", "job_title": "VP Eng", "email": "m@acmef20.example",
        "status": "new",
    })
    lead1 = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp, "company_id": co, "contact_id": ct1,
        "lead_status": "scored", "priority_tier": "A", "final_score": 0.9,
        "lifecycle_stage": "new",
    })
    lead2 = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp, "company_id": co, "contact_id": ct2,
        "lead_status": "scored", "priority_tier": "B", "final_score": 0.7,
        "lifecycle_stage": "new",
    })
    msg = repos.outreach_messages.create({
        "project_id": pid, "lead_id": lead1, "channel": "email",
        "subject": "hi", "body": "Hello there " + " ".join(["w"] * 60),
        "status": "sent",
    })
    reply = repos.outreach_replies.create({
        "outreach_message_id": msg, "from_email": "l@acmef20.example",
        "subject": "Re: hi", "body": "Sounds great, let's chat",
        "intent": "positive", "confidence": 0.85,
    })
    # Mark a delivered export so ingest_export_feedback exercises the auto-bridge.
    exp = repos.lead_exports.create({
        "project_id": pid, "icp_id": icp, "name": "smoke-export",
        "destination": "filesystem", "status": "delivered", "format": "csv",
        "row_count": 1, "artifact_path": "/tmp/fake.csv",
    })
    repos.lead_export_items.create({
        "lead_export_id": exp, "lead_id": lead2, "payload": {"lead_id": lead2},
    })
    return {
        "project_id": pid, "icp_id": icp, "lead1": lead1, "lead2": lead2,
        "message_id": msg, "reply_id": reply, "export_id": exp,
    }


def test_record_feedback(s: dict) -> None:
    res = record_feedback(
        repos, project_id=s["project_id"], kind="thumbs_up", source="human",
        lead_id=s["lead1"], outreach_message_id=s["message_id"],
        payload={"rater": "alex"}, weight=1.0,
    )
    assert res["event"]["kind"] == "thumbs_up"
    assert res["event"]["applied"] == 0
    res2 = record_feedback(
        repos, project_id=s["project_id"], kind="thumbs_down", source="human",
        lead_id=s["lead1"], outreach_message_id=s["message_id"],
    )
    assert res2["event"]["kind"] == "thumbs_down"
    print("✓ record_feedback (thumbs up/down)")


def test_invalid_transitions(s: dict) -> None:
    # Move lead2 to 'lost' (terminal), then attempt illegal jump.
    transition_lead(repos, lead_id=s["lead2"], to_status="contacted")
    transition_lead(repos, lead_id=s["lead2"], to_status="lost")
    try:
        transition_lead(repos, lead_id=s["lead2"], to_status="engaged")
    except ValueError as exc:
        assert "illegal transition" in str(exc), exc
        print("✓ ALLOWED_TRANSITIONS rejects illegal jump (lost -> engaged)")
        return
    raise AssertionError("expected ValueError for illegal transition")


def test_transition_writes_both(s: dict) -> None:
    # Use lead1 (still 'new'); advance to 'contacted'.
    res = transition_lead(repos, lead_id=s["lead1"], to_status="contacted",
                          reason="manual smoke", source="human")
    assert res["from_status"] == "new"
    assert res["to_status"] == "contacted"
    lead = repos.lead_candidates.get(s["lead1"])
    assert lead["lifecycle_stage"] == "contacted", lead
    transitions = repos.lifecycle_transitions.list_for_lead(s["lead1"])
    assert any(t["to_status"] == "contacted" for t in transitions)
    assert res["sync"]["synced"] is True
    print("✓ transition_lead writes lead_candidates + lifecycle_transitions + sync")


def test_apply_unapplied(s: dict) -> None:
    # Add a 'meeting_booked' feedback for lead1 (currently 'contacted').
    eid = record_feedback(
        repos, project_id=s["project_id"], kind="meeting_booked", source="human",
        lead_id=s["lead1"],
    )["event"]["id"]
    # Need to walk through: contacted -> engaged is allowed; meeting_booked needs engaged or qualified.
    # First advance contacted -> engaged.
    transition_lead(repos, lead_id=s["lead1"], to_status="engaged")
    res = apply_unapplied_feedback(repos, project_id=s["project_id"])
    assert res["applied"] >= 1
    after = repos.feedback_events.get(eid)
    assert after["applied"] == 1
    lead = repos.lead_candidates.get(s["lead1"])
    assert lead["lifecycle_stage"] == "meeting_booked", lead
    print("✓ apply_unapplied_feedback marks events + materializes transitions")


def test_ingest_reply_feedback(s: dict) -> None:
    reply = repos.outreach_replies.get(s["reply_id"])
    # lead1 is at meeting_booked already (terminal-ish for our test); ingest should not error.
    ev = ingest_reply_feedback(repos, reply)
    # Could be None if state machine refuses, but the event is recorded either way.
    # Find by reply_id in payload.
    events = repos.feedback_events.find({"project_id": s["project_id"], "source": "reply"})
    assert any((e.get("payload") or {}).get("reply_id") == s["reply_id"] for e in events), events
    print("✓ ingest_reply_feedback creates a reply-sourced feedback event")


def test_ingest_export_feedback_advances_new(s: dict) -> None:
    # lead2 is at 'lost' from earlier test; let's create a fresh lead 'new' -> contacted via export.
    fresh = repos.lead_candidates.create({
        "project_id": s["project_id"], "icp_id": s["icp_id"],
        "company_id": repos.contacts.get(s["lead2"] - s["lead2"] + 1) and 1 or 1,
        "contact_id": None, "lead_status": "scored",
        "priority_tier": "B", "final_score": 0.5, "lifecycle_stage": "new",
    })
    exp = repos.lead_exports.get(s["export_id"])
    items = [{"lead_id": fresh}]
    n = ingest_export_feedback(repos, exp, items)
    assert n == 1
    lead = repos.lead_candidates.get(fresh)
    assert lead["lifecycle_stage"] == "contacted", lead
    print("✓ ingest_export_feedback advances 'new' -> 'contacted'")


def test_pluggable_sync_adapter(s: dict) -> None:
    class Recorder:
        name = "recorder"

        def __init__(self) -> None:
            self.events: list[dict] = []

        def sync_transition(self, transition: dict, lead: dict) -> dict:
            self.events.append({"to": transition["to_status"], "lead": lead.get("id")})
            return {"synced": True, "adapter": "recorder"}

    rec = Recorder()
    set_default_lifecycle_sync_adapter(rec)
    try:
        # Move lead1 from meeting_booked → won (allowed)
        transition_lead(repos, lead_id=s["lead1"], to_status="won")
        assert any(e["to"] == "won" for e in rec.events), rec.events
        print("✓ pluggable LifecycleSyncAdapter override captured transition")
    finally:
        set_default_lifecycle_sync_adapter(None)
    assert isinstance(get_default_lifecycle_sync_adapter(), FakeLifecycleSyncAdapter)
    print("✓ set_default_lifecycle_sync_adapter(None) resets to FakeLifecycleSyncAdapter")


def test_pipeline_module(s: dict) -> None:
    run_id = pipeline_runner.run_now(
        run_type="feedback_ingestion",
        project_id=s["project_id"],
        icp_id=s["icp_id"],
        config={"include_replies": True, "include_exports": True},
    )
    summary = repos.pipeline_runs.get(run_id)
    assert summary and summary["status"] == "completed", summary
    print("✓ FeedbackIngestionModule via pipeline_runner.run_now")


def test_api_routes(s: dict) -> None:
    client = TestClient(app)
    pid = s["project_id"]

    r = client.post("/feedback", json={
        "project_id": pid, "kind": "note", "source": "human", "lead_id": s["lead2"],
        "payload": {"comment": "interesting"},
    })
    assert r.status_code == 200, r.text

    r = client.get("/feedback", params={"project_id": pid, "limit": 50})
    assert r.status_code == 200, r.text
    assert r.json()["count"] >= 1

    r = client.get("/feedback/summary", params={"project_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "by_kind" in body and "by_stage" in body and "recent" in body

    ev_id = repos.feedback_events.list_for_project(pid, limit=1)[0]["id"]
    r = client.get(f"/feedback/{ev_id}")
    assert r.status_code == 200

    r = client.post("/feedback/apply", json={"project_id": pid})
    assert r.status_code == 200

    r = client.get(f"/leads/{s['lead2']}/lifecycle")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lifecycle_stage"] == "lost"
    assert isinstance(body["transitions"], list)

    # Lead2 is at 'lost' (terminal) — transition request should 400.
    r = client.post(f"/leads/{s['lead2']}/transition",
                    json={"to_status": "engaged"})
    assert r.status_code == 400, r.text

    # 400: bad kind
    r = client.post("/feedback", json={"project_id": pid, "kind": "foobar"})
    assert r.status_code == 400

    # 400: bad to_status
    r = client.post(f"/leads/{s['lead2']}/transition", json={"to_status": "bogus"})
    assert r.status_code == 400

    # 404: missing lead
    r = client.get("/leads/999999/lifecycle")
    assert r.status_code == 404

    # 404: missing feedback event
    r = client.get("/feedback/999999")
    assert r.status_code == 404
    print("✓ API routes (7) + 400/404 validation")


def main() -> None:
    s = seed()
    test_record_feedback(s)
    test_transition_writes_both(s)
    test_invalid_transitions(s)
    test_apply_unapplied(s)
    test_ingest_reply_feedback(s)
    test_ingest_export_feedback_advances_new(s)
    test_pluggable_sync_adapter(s)
    test_pipeline_module(s)
    test_api_routes(s)
    print("\nALL FILE 20 FEEDBACK SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
