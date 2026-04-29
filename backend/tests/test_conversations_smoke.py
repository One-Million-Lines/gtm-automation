"""Smoke tests — File 23: Conversation Layer, Decision Traces, MultiTurnDrafter."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = str(Path(__file__).parent.parent)
sys.path.append(ROOT_DIR)

from fastapi.testclient import TestClient

import api_shared
from main import app
from pipeline.modules.multi_turn_drafter_module import (
    DraftResult,
    HeuristicReplyAdapter,
    ReplyDraftAdapter,
    get_default_reply_drafter,
    set_default_reply_drafter,
)
from services import conversation_service as svc

repos = api_shared.repos
runner = api_shared.pipeline_runner
client = TestClient(app)

print("=" * 70)
print("File 23 — Conversation layer smoke")
print("=" * 70)

# ── Seed ─────────────────────────────────────────────────────────────────────
project_id = repos.projects.create({"name": "ConvTest23"})
icp_id = repos.icps.create({
    "project_id": project_id,
    "name": "ICP23",
    "status": "active",
    "target_industries": ["saas"],
    "target_roles": ["cto"],
    "value_proposition": "boost reply rates 3x",
    "outreach_angle": "warm intro",
})
company_id = repos.companies.create({
    "name": "AcmeConv", "domain": "acmeconv.example", "industry": "saas",
    "status": "discovered",
})
contact_id = repos.contacts.create({
    "company_id": company_id, "first_name": "Lea", "last_name": "X",
    "full_name": "Lea X", "job_title": "CTO", "email": "lea@acmeconv.example",
    "status": "new",
})
lead_id = repos.lead_candidates.create({
    "project_id": project_id, "icp_id": icp_id, "company_id": company_id,
    "contact_id": contact_id, "lead_status": "scored", "priority_tier": "A",
    "final_score": 0.9,
})
msg_id = repos.outreach_messages.create({
    "project_id": project_id, "lead_id": lead_id, "channel": "email",
    "subject": "Quick thought on your growth", "body": "Hi Lea, " + "word " * 80,
    "status": "approved", "approved_at": "2025-01-01T00:00:00",
})
send_id = repos.outreach_sends.create({
    "outreach_message_id": msg_id, "provider": "fake",
    "status": "sent", "message_id_external": "ext-smoke-23",
    "attempted_at": "2025-01-01T10:00:00",
    "sent_at": "2025-01-01T10:00:00",
})
reply_id = repos.outreach_replies.create({
    "outreach_message_id": msg_id, "provider": "fake",
    "from_email": "lea@acmeconv.example",
    "body": "Sounds interesting, tell me more",
    "intent": "interested",
    "received_at": "2025-01-02T09:00:00",
})
print(f"project_id={project_id} lead_id={lead_id} send_id={send_id} reply_id={reply_id}")

# ── 1: Reconcile groups sends into threads ─────────────────────────────────
result = svc.rebuild_threads(repos, project_id=project_id)
assert result["created"] >= 1, f"Expected ≥1 thread created, got {result}"
print(f"✓ rebuild_threads: {result}")

# Verify thread was created
threads = repos.lead_threads.find_for_project(project_id)
assert len(threads) >= 1, "Expected at least 1 thread"
thread = threads[0]
assert thread["contact_id"] == contact_id
print(f"✓ thread created: id={thread['id']} status={thread['status']}")

# Reconcile is idempotent
result2 = svc.rebuild_threads(repos, project_id=project_id)
assert result2["created"] == 0, f"Second reconcile should create 0, got {result2['created']}"
assert result2["skipped"] >= 1, f"Second reconcile should skip ≥1, got {result2['skipped']}"
print(f"✓ reconcile idempotent: {result2}")

# ── 2: Thread has messages (send + reply) ─────────────────────────────────
thread_id = int(thread["id"])
detail = svc.get_thread_detail(repos, thread_id)
assert detail is not None
msgs = detail["messages"]
assert len(msgs) >= 2, f"Expected ≥2 messages, got {len(msgs)}"
directions = {m["direction"] for m in msgs}
assert "out" in directions and "in" in directions, f"Expected both directions, got {directions}"
print(f"✓ thread detail: {len(msgs)} messages with directions {directions}")

# ── 3: mark_status ──────────────────────────────────────────────────────────
updated = svc.mark_status(repos, thread_id, "awaiting_reply")
assert updated["status"] == "awaiting_reply"
print(f"✓ mark_status: status={updated['status']}")

# ── 4: add_manual_message ───────────────────────────────────────────────────
manual_msg = svc.add_manual_message(
    repos, thread_id, direction="out",
    subject="Following up", body_text="Just checking in"
)
assert manual_msg["source"] == "manual"
assert manual_msg["direction"] == "out"
print(f"✓ add_manual_message: id={manual_msg['id']}")

# ── 5: MultiTurnDrafterModule produces draft + decision_trace ───────────────
# Set thread back to awaiting_reply with last_direction=in for the drafter
repos.lead_threads.update(thread_id, {
    "status": "awaiting_reply", "last_direction": "in",
})

# Verify default adapter is Heuristic
adapter = get_default_reply_drafter()
assert isinstance(adapter, HeuristicReplyAdapter), f"Expected Heuristic, got {type(adapter)}"
print(f"✓ default adapter is HeuristicReplyAdapter")

run_id = runner.run_now(
    project_id=project_id,
    icp_id=icp_id,
    run_type="reply_drafter",
    config={"limit": 10},
)
run_detail = runner.get_run_detail(run_id)
assert run_detail["run"]["status"] in ("completed", "partially_completed"), (
    f"Expected completed, got {run_detail['run']['status']}"
)
print(f"✓ reply_drafter run_id={run_id} status={run_detail['run']['status']}")

# Check decision_trace was written
traces = repos.decision_traces.list_for_lead(lead_id)
assert len(traces) >= 1, "Expected at least 1 decision_trace"
trace = traces[0]
assert trace["decision_type"] == "draft"
assert trace["model_name"] == "heuristic"
print(f"✓ decision_trace: id={trace['id']} decision_type={trace['decision_type']} model={trace['model_name']}")

# Check reply_draft message added to thread
all_msgs = repos.lead_thread_messages.list_for_thread(thread_id)
draft_msgs = [m for m in all_msgs if m["source"] == "reply_draft"]
assert len(draft_msgs) >= 1, f"Expected reply_draft message, got sources={[m['source'] for m in all_msgs]}"
print(f"✓ reply_draft message persisted: {draft_msgs[-1]['subject']}")

# ── 6: Pluggable adapter swap ───────────────────────────────────────────────
class CustomTestAdapter:
    def draft(self, context: dict) -> DraftResult:
        return DraftResult(
            subject="CUSTOM SUBJECT",
            body_text="Custom deterministic body",
            rationale="custom adapter test",
            model_name="custom-test",
            confidence=0.99,
        )

assert isinstance(CustomTestAdapter(), ReplyDraftAdapter), "CustomTestAdapter should satisfy Protocol"
set_default_reply_drafter(CustomTestAdapter())
assert isinstance(get_default_reply_drafter(), CustomTestAdapter)
print(f"✓ adapter swap: {type(get_default_reply_drafter()).__name__}")
# Reset to heuristic
set_default_reply_drafter(HeuristicReplyAdapter())

# ── 7: Scheduler can fire a reply_drafter step via custom template ──────────
from services import orchestrator_service as orch_svc
tmpl = orch_svc.create_template(
    repos, project_id=project_id, name="Reply Drafter Tpl",
    slug="reply_drafter_tpl",
    steps=[{"run_type": "reply_drafter", "config": {"limit": 5}, "on_failure": "continue"}],
)
tpl_id = tmpl["id"]
run_result2 = orch_svc.run_template(
    repos, runner, template=tmpl, project_id=project_id
)
run_id2 = run_result2["steps"][0]["run_id"]
assert run_id2 is not None and run_id2 > 0
print(f"✓ scheduler template run_id={run_id2}")

# ── 8: API — GET /threads ───────────────────────────────────────────────────
resp = client.get("/threads", params={"project_id": project_id})
assert resp.status_code == 200, resp.text
data = resp.json()
assert data["count"] >= 1
print(f"✓ GET /threads count={data['count']}")

# ── 9: GET /threads/{id} ────────────────────────────────────────────────────
resp = client.get(f"/threads/{thread_id}")
assert resp.status_code == 200, resp.text
assert "messages" in resp.json()
print(f"✓ GET /threads/{thread_id} messages={len(resp.json()['messages'])}")

# ── 10: PATCH /threads/{id} ─────────────────────────────────────────────────
resp = client.patch(f"/threads/{thread_id}", json={"status": "closed"})
assert resp.status_code == 200, resp.text
assert resp.json()["status"] == "closed"
print(f"✓ PATCH /threads/{thread_id} status=closed")

# ── 11: POST /threads/{id}/messages ─────────────────────────────────────────
resp = client.post(f"/threads/{thread_id}/messages", json={
    "direction": "out", "subject": "API manual msg", "body_text": "hello from api",
})
assert resp.status_code == 201, resp.text
assert resp.json()["source"] == "manual"
print(f"✓ POST /threads/{thread_id}/messages id={resp.json()['id']}")

# ── 12: 404 checks ──────────────────────────────────────────────────────────
r1 = client.get("/threads/999999")
assert r1.status_code == 404
r2 = client.patch("/threads/999999", json={"status": "closed"})
assert r2.status_code == 404
print(f"✓ 404 checks pass")

# ── 13: POST /threads (create) ──────────────────────────────────────────────
resp = client.post("/threads", json={
    "project_id": project_id, "subject": "New manual thread", "status": "open",
})
assert resp.status_code == 201, resp.text
new_tid = resp.json()["id"]
assert new_tid > 0
print(f"✓ POST /threads created id={new_tid}")

# ── 14: GET /decision-traces ────────────────────────────────────────────────
resp = client.get("/decision-traces", params={"lead_id": lead_id})
assert resp.status_code == 200, resp.text
dt_data = resp.json()
assert dt_data["count"] >= 1
print(f"✓ GET /decision-traces count={dt_data['count']}")

resp2 = client.get("/decision-traces", params={"decision_type": "draft"})
assert resp2.status_code == 200
print(f"✓ GET /decision-traces?decision_type=draft count={resp2.json()['count']}")

# 400 on invalid decision_type
r_bad = client.get("/decision-traces", params={"decision_type": "bogus"})
assert r_bad.status_code == 400
print(f"✓ 400 on invalid decision_type")

# ── 15: GET /decision-traces/{id} ───────────────────────────────────────────
trace_id = traces[0]["id"]
resp = client.get(f"/decision-traces/{trace_id}")
assert resp.status_code == 200, resp.text
assert resp.json()["id"] == trace_id
print(f"✓ GET /decision-traces/{trace_id}")

r404 = client.get("/decision-traces/999999")
assert r404.status_code == 404
print(f"✓ 404 on missing decision_trace")

# ── 16: POST /threads/reconcile ─────────────────────────────────────────────
resp = client.post("/threads/reconcile", params={"project_id": project_id})
assert resp.status_code == 200, resp.text
print(f"✓ POST /threads/reconcile: {resp.json()}")

print()
print("=" * 70)
print("✅  All File 23 smoke tests passed")
print("=" * 70)
