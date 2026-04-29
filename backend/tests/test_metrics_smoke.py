"""Smoke test for File 17 — engagement metrics + campaign dashboard."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from api_shared import pipeline_runner, repos
from main import app
from services.engagement_aggregator import (
    FakeEngagementAggregator, SqlEngagementAggregator,
    compute_engagement, get_default_engagement_aggregator,
    set_default_engagement_aggregator,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def _seed_campaign(label: str = "metrics17") -> dict:
    """Seed project, icp, 1 company, 3 contacts, 3 leads, messages, sends, replies
    spread across multiple days + statuses + intents."""
    pid = repos.projects.create({"name": label, "slug": label})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP", "status": "active",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co_id = repos.companies.create({
        "name": "AcmeMetrics", "domain": f"{label}.example",
        "industry": "saas", "status": "qualified",
    })

    rows = []
    statuses_intents = [
        # (send_status, intent or None, days_ago)
        ("sent",     None,           0),   # plain sent today
        ("opened",   None,           1),
        ("replied",  "positive",     1),
        ("replied",  "negative",     2),
        ("replied",  "unsubscribe",  3),
        ("bounced",  None,           4),
        ("failed",   None,           5),
        ("replied",  "info_request", 7),
    ]
    for i, (sstatus, intent, days_ago) in enumerate(statuses_intents):
        ct = repos.contacts.create({
            "company_id": co_id,
            "first_name": "C", "last_name": str(i),
            "full_name": f"C {i}", "job_title": "CTO",
            "email": f"c{i}@{label}.example", "status": "new",
        })
        lead = repos.lead_candidates.create({
            "project_id": pid, "icp_id": icp_id,
            "company_id": co_id, "contact_id": ct,
            "lead_status": "scored", "priority_tier": "A", "final_score": 0.9,
        })
        msg_id = repos.outreach_messages.create({
            "project_id": pid, "lead_id": lead, "channel": "email",
            "subject": f"hi{i}", "body": "Hi " + " ".join(["w"] * 80),
            "status": "approved", "approved_at": "2025-01-01",
        })
        sent_iso = f"2026-04-{29 - days_ago:02d}T10:00:00"
        send_id = repos.outreach_sends.create({
            "outreach_message_id": msg_id,
            "provider": "fake",
            "to_email": f"c{i}@{label}.example",
            "status": sstatus,
            "attempted_at": sent_iso,
            "sent_at": sent_iso if sstatus in ("sent", "opened", "replied") else None,
            "message_id_external": f"ext-{label}-{i}",
        })
        if intent is not None:
            repos.outreach_replies.create({
                "outreach_message_id": msg_id,
                "outreach_send_id": send_id,
                "provider": "fake",
                "from_email": f"c{i}@{label}.example",
                "subject": "Re: hi",
                "body": "thanks",
                "intent": intent,
                "confidence": 0.9,
                "classifier": "fake",
                "received_at": sent_iso,
            })
        rows.append((msg_id, send_id, sstatus, intent))
    return {"project_id": pid, "icp_id": icp_id, "company_id": co_id, "rows": rows}


def main() -> int:
    failures: list[str] = []
    client = TestClient(app)

    # ------------------------------------------------------------------
    print("\n[default reset]")
    set_default_engagement_aggregator(None)
    agg = get_default_engagement_aggregator(repos)
    assertion(isinstance(agg, SqlEngagementAggregator),
              f"default aggregator is sql ({agg.name})", failures)

    # ------------------------------------------------------------------
    print("\n[seed campaign]")
    seed = _seed_campaign()
    pid = seed["project_id"]
    icp_id = seed["icp_id"]
    print(f"  PID={pid} ICP_ID={icp_id} rows={len(seed['rows'])}")

    # ------------------------------------------------------------------
    print("\n[SqlEngagementAggregator.compute (fresh)]")
    set_default_engagement_aggregator(None)
    m = compute_engagement(repos, pid, window_days=30, use_cache=False)
    # 8 rows, sent_count = sent+opened+replied = 1+1+4 = 6
    assertion(m["sent_count"] == 6, f"sent_count=6 (got {m['sent_count']})", failures)
    assertion(m["opened_count"] == 5, f"opened_count=5 (got {m['opened_count']})", failures)
    assertion(m["replied_count"] == 4, f"replied_count=4 (got {m['replied_count']})", failures)
    assertion(m["bounced_count"] == 1, f"bounced_count=1 (got {m['bounced_count']})", failures)
    assertion(m["failed_count"] == 1, f"failed_count=1 (got {m['failed_count']})", failures)
    assertion(round(m["reply_rate"], 4) == round(4 / 6, 4),
              f"reply_rate=4/6 (got {m['reply_rate']})", failures)
    assertion(round(m["positive_reply_rate"], 4) == round(1 / 6, 4),
              f"positive_reply_rate=1/6 (got {m['positive_reply_rate']})", failures)
    assertion(m["by_intent"].get("positive") == 1
              and m["by_intent"].get("unsubscribe") == 1,
              f"by_intent ({m['by_intent']})", failures)
    assertion(m["unsubscribed_count"] == 1,
              f"unsubscribed_count=1 ({m['unsubscribed_count']})", failures)
    assertion(isinstance(m["daily_series"], list) and len(m["daily_series"]) >= 1,
              f"daily_series has rows ({len(m['daily_series'])})", failures)
    f = m["funnel"]
    assertion(f["sent"] == 6 and f["replied"] == 4 and f["positive"] == 1,
              f"funnel ({f})", failures)
    assertion(m["from_cache"] is False, "from_cache=False on first compute", failures)

    # ------------------------------------------------------------------
    print("\n[cache hit on second compute]")
    m2 = compute_engagement(repos, pid, window_days=30, use_cache=True)
    assertion(m2["from_cache"] is True, "from_cache=True on second compute", failures)
    assertion(m2["sent_count"] == m["sent_count"], "cached sent_count matches", failures)

    # ------------------------------------------------------------------
    print("\n[snapshot upserted]")
    snap = repos.engagement_snapshots.latest_for(pid, icp_id=None, window_days=30)
    assertion(snap is not None and snap["payload"]["sent_count"] == 6,
              f"snapshot persisted ({snap and snap.get('id')})", failures)

    # ------------------------------------------------------------------
    print("\n[FakeEngagementAggregator]")
    fake = FakeEngagementAggregator({"sent_count": 999, "reply_rate": 0.5})
    set_default_engagement_aggregator(fake)
    fake_m = compute_engagement(repos, pid)
    assertion(fake_m["sent_count"] == 999, "fake aggregator returns its payload", failures)
    set_default_engagement_aggregator(None)

    # ------------------------------------------------------------------
    print("\n[API: GET /metrics/campaign]")
    r = client.get(f"/metrics/campaign?project_id={pid}&window_days=30")
    assertion(r.status_code == 200 and r.json().get("sent_count") == 6,
              f"GET /metrics/campaign ({r.status_code} {r.text[:200]})", failures)

    print("\n[API: GET /metrics/campaign?recompute=true]")
    r = client.get(f"/metrics/campaign?project_id={pid}&window_days=30&recompute=true")
    assertion(r.status_code == 200 and r.json().get("from_cache") is False,
              f"recompute fresh ({r.status_code})", failures)

    print("\n[API: GET /metrics/series]")
    r = client.get(f"/metrics/series?project_id={pid}&window_days=30")
    body = r.json()
    assertion(r.status_code == 200 and isinstance(body.get("series"), list)
              and len(body["series"]) >= 1,
              f"GET /metrics/series ({r.status_code} {body})", failures)
    first = body["series"][0]
    assertion(set(first.keys()) >= {"date", "sent", "opened", "replied", "bounced"},
              f"series row shape ({first})", failures)

    print("\n[API: GET /metrics/funnel]")
    r = client.get(f"/metrics/funnel?project_id={pid}")
    body = r.json()
    assertion(r.status_code == 200 and body.get("funnel", {}).get("sent") == 6,
              f"GET /metrics/funnel ({r.status_code} {body})", failures)

    print("\n[API: POST /metrics/recompute]")
    r = client.post("/metrics/recompute", json={"project_id": pid, "window_days": 7})
    body = r.json()
    assertion(r.status_code == 200 and body.get("ok") is True
              and body["window_days"] == 7,
              f"POST /metrics/recompute ({r.status_code} {body})", failures)

    print("\n[API: 404s + 400s]")
    r = client.get("/metrics/campaign?project_id=999999")
    assertion(r.status_code == 404, f"campaign 404 ({r.status_code})", failures)
    r = client.get("/metrics/series?project_id=999999")
    assertion(r.status_code == 404, f"series 404 ({r.status_code})", failures)
    r = client.get("/metrics/funnel?project_id=999999")
    assertion(r.status_code == 404, f"funnel 404 ({r.status_code})", failures)
    r = client.post("/metrics/recompute", json={})
    assertion(r.status_code == 400, f"recompute 400 ({r.status_code})", failures)
    r = client.post("/metrics/recompute", json={"project_id": 999999})
    assertion(r.status_code == 404, f"recompute 404 ({r.status_code})", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=engagement_metrics]")
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="engagement_metrics",
        config={"window_days": 30, "recompute": True},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

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
