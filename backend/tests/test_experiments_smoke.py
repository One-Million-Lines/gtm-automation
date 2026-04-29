"""Smoke test for File 18 — A/B variant testing + multivariate experiments."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from api_shared import pipeline_runner, repos
from main import app
from services.experiment_service import (
    assign_lead_to_experiment, create_experiment, declare_winner,
    score_experiment, wilson_lower_bound,
)
from services.variant_allocator import (
    FakeVariantAllocator, HashVariantAllocator, RandomVariantAllocator,
    allocate_variant, set_default_variant_allocator,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def _seed_project(label: str = "exp18") -> dict:
    pid = repos.projects.create({"name": label, "slug": label})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP", "status": "active",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co_id = repos.companies.create({
        "name": f"Acme-{label}", "domain": f"{label}.example",
        "industry": "saas", "status": "qualified",
    })
    return {"project_id": pid, "icp_id": icp_id, "company_id": co_id}


def _seed_send(repos_, *, project_id, icp_id, company_id, variant_id,
               status="sent", intent=None, suffix=""):
    ct = repos_.contacts.create({
        "company_id": company_id,
        "first_name": "C", "last_name": suffix,
        "full_name": f"C {suffix}", "job_title": "CTO",
        "email": f"c{suffix}@x.example", "status": "new",
    })
    lead = repos_.lead_candidates.create({
        "project_id": project_id, "icp_id": icp_id,
        "company_id": company_id, "contact_id": ct,
        "lead_status": "scored", "priority_tier": "A", "final_score": 0.9,
    })
    msg_id = repos_.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": f"hi-{suffix}", "body": "Hi " + " ".join(["w"] * 80),
        "status": "approved", "approved_at": "2025-01-01",
        "variant_id": int(variant_id),
    })
    send_id = repos_.outreach_sends.create({
        "outreach_message_id": msg_id,
        "provider": "fake",
        "to_email": f"c{suffix}@x.example",
        "status": status,
        "attempted_at": "2026-04-29T10:00:00",
        "sent_at": "2026-04-29T10:00:00" if status in ("sent", "opened", "replied") else None,
        "message_id_external": f"ext-{suffix}",
    })
    if intent is not None:
        repos_.outreach_replies.create({
            "outreach_message_id": msg_id,
            "outreach_send_id": send_id,
            "provider": "fake",
            "from_email": f"c{suffix}@x.example",
            "subject": "Re: hi", "body": "thanks",
            "intent": intent, "confidence": 0.9, "classifier": "fake",
            "received_at": "2026-04-29T10:00:00",
        })
    return lead, msg_id


def main() -> int:
    failures: list[str] = []
    client = TestClient(app)

    # ------------------------------------------------------------------
    print("\n[allocator: hash determinism]")
    set_default_variant_allocator(None)
    fake_exp = {"id": 42}
    variants = [{"id": 1, "name": "A", "weight": 1.0}, {"id": 2, "name": "B", "weight": 1.0}]
    h1 = allocate_variant(fake_exp, variants, 7)
    h2 = allocate_variant(fake_exp, variants, 7)
    h3 = allocate_variant(fake_exp, variants, 7)
    assertion(h1["id"] == h2["id"] == h3["id"],
              f"hash determinism for lead 7 -> {h1['id']}", failures)

    # ------------------------------------------------------------------
    print("\n[allocator: 60/40 weight distribution over 1000 leads]")
    variants_w = [{"id": 1, "name": "A", "weight": 0.6}, {"id": 2, "name": "B", "weight": 0.4}]
    counts = {1: 0, 2: 0}
    for lid in range(1000):
        v = allocate_variant({"id": 99}, variants_w, lid)
        counts[int(v["id"])] += 1
    a_pct = counts[1] / 1000.0
    assertion(0.53 <= a_pct <= 0.67,
              f"60/40 distribution: A={a_pct:.3f} (target 0.60 ±0.07)", failures)

    # ------------------------------------------------------------------
    print("\n[allocator: random + fake]")
    rnd = RandomVariantAllocator(seed=123)
    rv = rnd.allocate({"id": 1}, variants, 1)
    assertion(rv["id"] in (1, 2), f"random returns a variant ({rv['id']})", failures)
    fk = FakeVariantAllocator(forced_variant_index=1)
    fkv = fk.allocate({"id": 1}, variants, 1)
    assertion(fkv["id"] == 2, f"fake forced index=1 -> id=2 (got {fkv['id']})", failures)

    # ------------------------------------------------------------------
    print("\n[create_experiment + assignment idempotency]")
    seed = _seed_project()
    pid = seed["project_id"]
    icp_id = seed["icp_id"]
    co_id = seed["company_id"]

    exp = create_experiment(
        repos,
        project_id=pid, icp_id=icp_id, name="subject_test",
        hypothesis="short subject lines outperform long ones",
        variants=[
            {"name": "control_long", "weight": 1.0,
             "subject_template": "A long subject line for {first_name}",
             "body_template": "Hi {first_name}, body."},
            {"name": "short", "weight": 1.0,
             "subject_template": "Hi {first_name}",
             "body_template": "Hi {first_name}, body."},
        ],
        min_sample_size=4,
    )
    assertion(exp["status"] == "draft", f"experiment created status=draft", failures)
    assertion(len(exp["variants"]) == 2, f"2 variants embedded", failures)
    assertion(exp["variants"][0]["is_control"] in (1, True),
              f"first variant flagged as control", failures)

    # Need a lead first
    ct = repos.contacts.create({
        "company_id": co_id, "first_name": "L", "last_name": "X",
        "full_name": "L X", "job_title": "CTO",
        "email": "l@x.example", "status": "new",
    })
    lead = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co_id, "contact_id": ct,
        "lead_status": "scored", "priority_tier": "A", "final_score": 0.9,
    })

    a1 = assign_lead_to_experiment(repos, lead, int(exp["id"]))
    a2 = assign_lead_to_experiment(repos, lead, int(exp["id"]))
    assertion(a1["id"] == a2["id"],
              f"assignment idempotent ({a1['id']} == {a2['id']})", failures)
    assertion(a1["variant_id"] in [v["id"] for v in exp["variants"]],
              f"variant_id valid", failures)

    # ------------------------------------------------------------------
    print("\n[seed sends + score_experiment]")
    # Variant A (control): 5 sent, 0 positive replies (low rate)
    v_control_id = next(v["id"] for v in exp["variants"] if v.get("is_control"))
    v_other_id = next(v["id"] for v in exp["variants"] if not v.get("is_control"))

    for i in range(5):
        _seed_send(repos, project_id=pid, icp_id=icp_id, company_id=co_id,
                   variant_id=v_control_id, status="sent", intent=None,
                   suffix=f"cA{i}")
    # Variant B (challenger): 5 sent, 4 positive
    for i in range(5):
        _seed_send(repos, project_id=pid, icp_id=icp_id, company_id=co_id,
                   variant_id=v_other_id,
                   status="replied" if i < 4 else "sent",
                   intent="positive" if i < 4 else None,
                   suffix=f"cB{i}")

    score = score_experiment(repos, int(exp["id"]))
    by = {v["variant_id"]: v for v in score["by_variant"]}
    assertion(by[v_control_id]["sent"] == 5 and by[v_control_id]["positive"] == 0,
              f"control: sent=5 positive=0 (got s={by[v_control_id]['sent']} p={by[v_control_id]['positive']})",
              failures)
    assertion(by[v_other_id]["sent"] == 5 and by[v_other_id]["positive"] == 4,
              f"challenger: sent=5 positive=4 (got s={by[v_other_id]['sent']} p={by[v_other_id]['positive']})",
              failures)
    assertion(by[v_other_id]["positive_reply_rate"] == 0.8,
              f"challenger positive_reply_rate=0.8 (got {by[v_other_id]['positive_reply_rate']})",
              failures)
    # Wilson math sanity
    wlb = round(wilson_lower_bound(4, 5), 4)
    assertion(by[v_other_id]["wilson_lower"] == wlb,
              f"wilson_lower matches helper ({by[v_other_id]['wilson_lower']} == {wlb})",
              failures)
    assertion(score["leader_variant_id"] == v_other_id,
              f"leader = challenger ({score['leader_variant_id']})", failures)
    assertion(score["ready_to_declare"] is True,
              f"ready_to_declare=True (sent>=min, wilson>control_pos_rate)",
              failures)

    # ------------------------------------------------------------------
    print("\n[declare_winner]")
    res = declare_winner(repos, int(exp["id"]), int(v_other_id))
    assertion(res["status"] == "completed",
              f"experiment status=completed (got {res['status']})", failures)
    assertion(int(res["winner_variant_id"]) == int(v_other_id),
              f"winner_variant_id={v_other_id} (got {res.get('winner_variant_id')})",
              failures)

    # ------------------------------------------------------------------
    print("\n[ExperimentScoringModule via pipeline_runner with auto_declare]")
    # Build a second experiment + sends so auto_declare can fire.
    exp2 = create_experiment(
        repos,
        project_id=pid, icp_id=icp_id, name="cta_test",
        variants=[
            {"name": "control", "weight": 1.0,
             "subject_template": "S", "body_template": "B"},
            {"name": "ctaB", "weight": 1.0,
             "subject_template": "S2", "body_template": "B2"},
        ],
        min_sample_size=3, status="running",
    )
    v2_ctl = next(v["id"] for v in exp2["variants"] if v.get("is_control"))
    v2_ch = next(v["id"] for v in exp2["variants"] if not v.get("is_control"))
    for i in range(4):
        _seed_send(repos, project_id=pid, icp_id=icp_id, company_id=co_id,
                   variant_id=v2_ctl, status="sent", intent=None,
                   suffix=f"e2A{i}")
    for i in range(4):
        _seed_send(repos, project_id=pid, icp_id=icp_id, company_id=co_id,
                   variant_id=v2_ch,
                   status="replied", intent="positive",
                   suffix=f"e2B{i}")

    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="experiment_scoring",
        config={"auto_declare": True},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"pipeline run completed -> {status}", failures)

    exp2_after = repos.outreach_experiments.get(int(exp2["id"]))
    assertion(exp2_after["status"] == "completed",
              f"exp2 auto-declared completed (got {exp2_after['status']})", failures)
    assertion(int(exp2_after["winner_variant_id"]) == int(v2_ch),
              f"exp2 winner = challenger ({exp2_after.get('winner_variant_id')})",
              failures)

    # ------------------------------------------------------------------
    print("\n[API: 7 routes]")
    r = client.post("/experiments", json={
        "project_id": pid, "icp_id": icp_id, "name": "api_test",
        "variants": [
            {"name": "v1", "weight": 1.0, "subject_template": "s1", "body_template": "b1"},
            {"name": "v2", "weight": 1.0, "subject_template": "s2", "body_template": "b2"},
        ],
    })
    assertion(r.status_code == 200 and r.json().get("status") == "draft",
              f"POST /experiments ({r.status_code})", failures)
    api_exp_id = int(r.json()["id"])
    api_v1 = int(r.json()["variants"][0]["id"])
    api_v2 = int(r.json()["variants"][1]["id"])

    r = client.get(f"/experiments?project_id={pid}")
    assertion(r.status_code == 200 and r.json().get("count", 0) >= 1,
              f"GET /experiments ({r.status_code})", failures)

    r = client.get(f"/experiments/{api_exp_id}")
    body = r.json()
    assertion(r.status_code == 200 and "experiment" in body and "variants" in body
              and "score" in body and "assignments_count" in body,
              f"GET /experiments/{{id}} ({r.status_code})", failures)

    r = client.post(f"/experiments/{api_exp_id}/start")
    assertion(r.status_code == 200 and r.json().get("status") == "running",
              f"POST start ({r.status_code} {r.json().get('status')})", failures)

    r = client.post(f"/experiments/{api_exp_id}/pause")
    assertion(r.status_code == 200 and r.json().get("status") == "paused",
              f"POST pause ({r.status_code} {r.json().get('status')})", failures)

    r = client.post(f"/experiments/{api_exp_id}/score")
    assertion(r.status_code == 200 and "by_variant" in r.json(),
              f"POST score ({r.status_code})", failures)

    r = client.post(f"/experiments/{api_exp_id}/declare", json={"variant_id": api_v2})
    assertion(r.status_code == 200 and r.json().get("status") == "completed",
              f"POST declare ({r.status_code} {r.json().get('status')})", failures)

    # ------------------------------------------------------------------
    print("\n[API: 400/404]")
    r = client.post("/experiments", json={})
    assertion(r.status_code == 400, f"POST empty -> 400 ({r.status_code})", failures)
    r = client.post("/experiments", json={"project_id": pid, "name": "x", "variants": []})
    assertion(r.status_code == 400, f"POST no variants -> 400 ({r.status_code})", failures)
    r = client.post("/experiments", json={"project_id": 999999, "name": "x",
                                          "variants": [{"name": "a"}]})
    assertion(r.status_code == 404, f"POST missing proj -> 404 ({r.status_code})", failures)
    r = client.get("/experiments?project_id=999999")
    assertion(r.status_code == 404, f"GET list missing proj -> 404 ({r.status_code})", failures)
    r = client.get(f"/experiments?project_id={pid}&status=invalid")
    assertion(r.status_code == 400, f"GET list bad status -> 400 ({r.status_code})", failures)
    r = client.get("/experiments/999999")
    assertion(r.status_code == 404, f"GET missing -> 404 ({r.status_code})", failures)
    r = client.post("/experiments/999999/start")
    assertion(r.status_code == 404, f"start missing -> 404 ({r.status_code})", failures)
    r = client.post(f"/experiments/{api_exp_id}/declare", json={})
    assertion(r.status_code == 400, f"declare no variant_id -> 400 ({r.status_code})", failures)

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
