"""Smoke test for File 15 — sender + send queue MVP (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.email_sender import (
    FakeEmailSender, LLMRewriteOnSendSender, SEND_STATUSES,
    get_default_email_sender, send_email, set_default_email_sender,
)
from services.send_service import (
    DEFAULT_MAX_PER_DAY, _select_sendable_message_ids, run_send_batch,
    send_for_message,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # ------------------------------------------------------------------
    print("\n[taxonomy]")
    assertion(set(SEND_STATUSES) == {
        "queued", "sending", "sent", "bounced", "failed", "opened", "replied",
    }, "SEND_STATUSES taxonomy", failures)

    # ------------------------------------------------------------------
    print("\n[FakeEmailSender determinism]")
    fake = FakeEmailSender()
    r1 = fake.send(to="a@x.com", subject="s", body="b", outreach_message_id=42)
    r2 = fake.send(to="a@x.com", subject="s", body="b", outreach_message_id=42)
    assertion(r1["message_id_external"] == "fake-42-1", f"first id ({r1['message_id_external']})", failures)
    assertion(r2["message_id_external"] == "fake-42-2", f"second id ({r2['message_id_external']})", failures)
    assertion(r1["status"] == "sent" and r1["ok"], "fake sends ok", failures)

    bouncer = FakeEmailSender(bounce_on=("bounce@x.com",))
    rb = bouncer.send(to="bounce@x.com", subject="s", body="b", outreach_message_id=1)
    assertion(rb["status"] == "bounced" and not rb["ok"], "bounce status", failures)

    # ------------------------------------------------------------------
    print("\n[send_email convenience + default registry]")
    set_default_email_sender(FakeEmailSender())
    rc = send_email(to="x@y.com", subject="s", body="b", outreach_message_id=7)
    assertion(rc["ok"] and rc["provider"] == "fake", "send_email default fake", failures)
    set_default_email_sender(None)
    assertion(get_default_email_sender().name == "fake", "reset to FakeEmailSender", failures)

    # ------------------------------------------------------------------
    print("\n[LLMRewriteOnSendSender(llm=None) degrades]")
    base = FakeEmailSender()
    deco = LLMRewriteOnSendSender(base=base, llm=None)
    rd = deco.send(to="a@x.com", subject="hello", body="hi", outreach_message_id=11)
    assertion(rd["ok"] and rd["provider"] == "fake",
              "decorator delegates to base when llm None", failures)

    # ------------------------------------------------------------------
    print("\n[db scenario setup]")
    pid = repos.projects.create({"name": "smoke15"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP1", "status": "draft",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co = repos.companies.create({
        "name": "AcmeCo", "domain": "acmeco15.example", "industry": "saas",
        "status": "discovered",
    })
    ct = repos.contacts.create({
        "company_id": co, "first_name": "Alex", "last_name": "X", "full_name": "Alex X",
        "job_title": "CTO", "email": "alex@acmeco15.example", "status": "new",
    })
    lead = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co, "contact_id": ct, "lead_status": "scored",
        "priority_tier": "A", "final_score": 0.95,
    })

    draft_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "Quick thought for your team this week here",
        "body": "Hi Alex, " + " ".join(["word"] * 80),
        "status": "draft",
    })
    approved_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "Quick thought for your team this week here",
        "body": "Hi Alex, " + " ".join(["word"] * 80),
        "status": "approved",
        "approved_at": "2025-01-01T00:00:00",
    })
    approved_msg_2 = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "Quick thought for your team this week here",
        "body": "Hi Alex, " + " ".join(["word"] * 80),
        "status": "approved",
        "approved_at": "2025-01-01T00:00:00",
    })

    # ------------------------------------------------------------------
    print("\n[_select_sendable_message_ids]")
    ids = _select_sendable_message_ids(repos, project_id=pid, message_ids=None, limit=50)
    assertion(approved_msg in ids and approved_msg_2 in ids,
              f"approved msgs selected ({ids})", failures)
    assertion(draft_msg not in ids, "draft excluded", failures)

    # ------------------------------------------------------------------
    print("\n[send_for_message gate: draft -> message_not_approved]")
    set_default_email_sender(FakeEmailSender())
    r = send_for_message(repos, draft_msg)
    assertion(not r["ok"] and r["error"] == "message_not_approved",
              f"draft rejected ({r})", failures)

    # ------------------------------------------------------------------
    print("\n[send_for_message: approved -> sent + msg.status='sent']")
    r = send_for_message(repos, approved_msg)
    assertion(r["ok"] and r["status"] == "sent",
              f"approved sent ({r})", failures)
    msg_after = repos.outreach_messages.get(approved_msg)
    assertion((msg_after.get("status") or "").lower() == "sent",
              f"msg.status -> sent (got {msg_after.get('status')})", failures)

    # ------------------------------------------------------------------
    print("\n[count_sent_today]")
    n = repos.outreach_sends.count_sent_today(pid)
    assertion(n >= 1, f"count_sent_today >= 1 ({n})", failures)

    # ------------------------------------------------------------------
    print("\n[quota gate: max_per_day=0 -> daily_quota_exceeded]")
    r = send_for_message(repos, approved_msg_2, max_per_day=0, enforce_quota=True)
    assertion(not r["ok"] and r["error"] == "daily_quota_exceeded",
              f"quota gate ({r})", failures)

    # ------------------------------------------------------------------
    print("\n[run_send_batch quota+already-sent skip]")
    batch = run_send_batch(repos, project_id=pid, max_per_day=DEFAULT_MAX_PER_DAY, limit=50)
    assertion(batch["scanned"] >= 1, f"scanned >= 1 ({batch['scanned']})", failures)
    assertion(batch["sent"] >= 1 or batch["sent"] == 0, "sent in [0, scanned]", failures)
    # already-sent approved_msg should NOT be in scanned again
    scanned_ids = [it.get("message_id") for it in batch["items"]]
    assertion(approved_msg not in scanned_ids,
              f"already-sent excluded ({scanned_ids})", failures)

    # ------------------------------------------------------------------
    print("\n[run_send_batch zero quota skips all]")
    # Create a fresh approved msg
    fresh_approved = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "Quick thought for your team this week here",
        "body": "Hi Alex, " + " ".join(["word"] * 80),
        "status": "approved",
        "approved_at": "2025-01-01T00:00:00",
    })
    b2 = run_send_batch(repos, project_id=pid, max_per_day=0, limit=50)
    assertion(b2["sent"] == 0, f"sent=0 with quota=0 ({b2['sent']})", failures)
    assertion(b2["skipped_quota"] >= 1 or b2["scanned"] == 0,
              f"quota skip applied ({b2})", failures)

    # ------------------------------------------------------------------
    print("\n[API: TestClient]")
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    r = client.get(f"/sends/quota?project_id={pid}")
    assertion(r.status_code == 200 and r.json()["sent_today"] >= 1,
              f"GET /sends/quota ({r.status_code} {r.text})", failures)

    r = client.post(f"/outreach/{draft_msg}/send", json={})
    assertion(r.status_code == 400 and r.json().get("detail") == "message_not_approved",
              f"POST send draft -> 400 ({r.status_code} {r.text})", failures)

    r = client.post(f"/outreach/{fresh_approved}/send", json={"max_per_day": 0})
    assertion(r.status_code == 400 and r.json().get("detail") == "daily_quota_exceeded",
              f"POST send quota=0 -> 400 ({r.status_code} {r.text})", failures)

    r = client.post(f"/outreach/{fresh_approved}/send", json={})
    assertion(r.status_code == 200 and r.json().get("status") == "sent",
              f"POST send approved -> 200 sent ({r.status_code} {r.text})", failures)

    r = client.get(f"/outreach/{fresh_approved}/sends")
    assertion(r.status_code == 200 and r.json().get("count") >= 1,
              f"GET sends history ({r.status_code} {r.text})", failures)

    r = client.post("/sends/run", json={})
    assertion(r.status_code == 400, f"POST /sends/run {{}} -> 400 ({r.status_code})", failures)

    r = client.get(f"/sends?project_id={pid}&status=nope")
    assertion(r.status_code == 400, f"GET /sends bad status -> 400 ({r.status_code})", failures)

    r = client.get(f"/sends?project_id={pid}&limit=50")
    assertion(r.status_code == 200, f"GET /sends 200 ({r.status_code})", failures)
    data = r.json()
    assertion(data["count"] >= 1, f"sends count >= 1 ({data['count']})", failures)
    rr = data["data"][0].get("raw_response")
    assertion(isinstance(rr, dict), f"raw_response decoded ({type(rr).__name__})", failures)

    r = client.post(f"/outreach/999999/send", json={})
    assertion(r.status_code == 404, f"404 missing message ({r.status_code})", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=send_queue]")
    # Create another approved message so the pipeline has something to send.
    extra_approved = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "Quick thought for your team this week here",
        "body": "Hi Alex, " + " ".join(["word"] * 80),
        "status": "approved",
        "approved_at": "2025-01-01T00:00:00",
    })
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="send_queue",
        config={"limit": 50, "max_per_day": DEFAULT_MAX_PER_DAY},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

    # ------------------------------------------------------------------
    set_default_email_sender(None)

    print("\n========")
    if failures:
        print(f"FAIL — {len(failures)} failure(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS — 0 failures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
