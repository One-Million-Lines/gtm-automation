"""Smoke test for File 14 — quality control + send-ready gate (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.outreach_generator import OUTREACH_STATUSES
from services.quality_checker import (
    FakeQualityChecker, QUALITY_RULES, RuleBasedQualityChecker, SPAM_TRIGGERS,
    _aggregate_score, _check_suppression, _scan_merge_tags, _scan_pii,
    _scan_spam_words, set_default_quality_checker,
)
from services.quality_service import (
    quality_check_for_message, run_quality_batch,
)


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def _good_subject() -> str:
    return "Quick thought for your team this week here"  # 49 chars, in 30-80


def _good_body() -> str:
    # Aim for 80 words: "word " * 80
    return " ".join(["word"] * 80)


def main() -> int:
    failures: list[str] = []

    # ------------------------------------------------------------------
    print("\n[helpers]")
    assertion(_scan_merge_tags("hi {{name}} and [[var]]") == ["{{name}}", "[[var]]"],
              "merge tag scan", failures)
    assertion(len(_scan_pii("call me at +1 415-555-2671 today")) >= 1,
              "phone pii detected", failures)
    assertion(len(_scan_pii("ssn 123-45-6789")) >= 1, "ssn pii detected", failures)
    assertion(_scan_spam_words("act now and earn $$$") == ["act now", "earn $"]
              or "act now" in _scan_spam_words("act now and earn $$$"),
              "spam word scan", failures)
    assertion(len(SPAM_TRIGGERS) == 30, "30 spam triggers", failures)
    assertion(set(QUALITY_RULES) == {
        "subject_length", "body_word_count", "merge_tags",
        "pii", "suppression", "spam_words",
    }, "rule taxonomy", failures)
    assertion(_aggregate_score([
        {"rule": "x", "passed": True, "weight": 1.0},
        {"rule": "y", "passed": False, "weight": 1.0},
    ]) == 0.5, "aggregate score 0.5", failures)
    assertion(_aggregate_score([
        {"rule": "pii", "passed": False, "weight": 2.0},
        {"rule": "x", "passed": True, "weight": 1.0},
    ]) == 0.0, "critical fail collapses to 0", failures)

    # ------------------------------------------------------------------
    print("\n[db scenario setup]")
    pid = repos.projects.create({"name": "smoke14"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP1", "status": "draft",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co = repos.companies.create({
        "name": "AcmeCo", "domain": "acmeco14.example", "industry": "saas",
        "status": "discovered",
    })
    ct = repos.contacts.create({
        "company_id": co, "first_name": "Alex", "last_name": "X", "full_name": "Alex X",
        "job_title": "CTO", "email": "alex@acmeco14.example", "status": "new",
    })
    lead = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co, "contact_id": ct, "lead_status": "scored",
        "priority_tier": "A", "final_score": 0.95,
    })

    good_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": _good_subject(),
        "body": _good_body(),
        "status": "draft",
    })
    bad_subject_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "hi",  # too short
        "body": _good_body(),
        "status": "draft",
    })
    merge_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": _good_subject(),
        "body": _good_body() + " hi {{name}}",
        "status": "draft",
    })
    spam_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": _good_subject(),
        "body": _good_body() + " act now! amazing free trial - earn $ today",
        "status": "draft",
    })

    # ------------------------------------------------------------------
    print("\n[RuleBasedQualityChecker — good message passes]")
    res_good = quality_check_for_message(repos, good_msg)
    assertion(res_good["ok"], "ok", failures)
    assertion(res_good["passed"], f"passed (score={res_good['score']})", failures)
    assertion(res_good["score"] >= 0.6, "score >= 0.6", failures)
    rules = {r["rule"]: r for r in res_good["rule_results"]}
    assertion(rules["subject_length"]["passed"], "subject_length pass", failures)
    assertion(rules["body_word_count"]["passed"], "body_word_count pass", failures)
    assertion(rules["merge_tags"]["passed"], "merge_tags pass", failures)
    assertion(rules["pii"]["passed"], "pii pass", failures)
    assertion(rules["suppression"]["passed"], "suppression pass", failures)
    assertion(rules["spam_words"]["passed"], "spam_words pass", failures)

    # ------------------------------------------------------------------
    print("\n[short subject fires rule]")
    res_bs = quality_check_for_message(repos, bad_subject_msg)
    rules = {r["rule"]: r for r in res_bs["rule_results"]}
    assertion(not rules["subject_length"]["passed"], "subject_length fail", failures)

    # ------------------------------------------------------------------
    print("\n[merge-tag leftover fires rule]")
    res_mt = quality_check_for_message(repos, merge_msg)
    rules = {r["rule"]: r for r in res_mt["rule_results"]}
    assertion(not rules["merge_tags"]["passed"], "merge_tags fail", failures)

    # ------------------------------------------------------------------
    print("\n[spam trigger fires rule]")
    res_sp = quality_check_for_message(repos, spam_msg)
    rules = {r["rule"]: r for r in res_sp["rule_results"]}
    assertion(not rules["spam_words"]["passed"], "spam_words fail", failures)

    # ------------------------------------------------------------------
    print("\n[suppression hit fires rule]")
    repos.suppression.add("email", "alex@acmeco14.example", reason="manual")
    sup = _check_suppression(repos, repos.contacts.get(ct))
    assertion(sup["hit"], "helper detects hit", failures)
    res_sup = quality_check_for_message(repos, good_msg)
    rules = {r["rule"]: r for r in res_sup["rule_results"]}
    assertion(not rules["suppression"]["passed"], "suppression fail", failures)
    assertion(res_sup["score"] == 0.0, "score collapses to 0", failures)
    assertion(not res_sup["passed"], "passed=False after suppression hit", failures)

    # ------------------------------------------------------------------
    print("\n[dry_run no-write]")
    before = len(repos.quality_checks.history_for_message(good_msg))
    dr = quality_check_for_message(repos, good_msg, dry_run=True)
    after = len(repos.quality_checks.history_for_message(good_msg))
    assertion(dr["persisted"] is False, "persisted=False", failures)
    assertion(after == before, "history unchanged", failures)

    # ------------------------------------------------------------------
    print("\n[history grows]")
    quality_check_for_message(repos, good_msg)
    new_count = len(repos.quality_checks.history_for_message(good_msg))
    assertion(new_count >= before + 1, f"history grew ({before}->{new_count})", failures)

    # ------------------------------------------------------------------
    print("\n[FakeQualityChecker installed]")
    fake = FakeQualityChecker(fixed_score=0.99, fixed_passed=True)
    set_default_quality_checker(fake)
    res_fake = quality_check_for_message(repos, bad_subject_msg)
    assertion(res_fake["checker"] == "fake", "checker=fake", failures)
    assertion(res_fake["passed"] is True, "fake forces passed", failures)
    set_default_quality_checker(None)  # restore real

    # ------------------------------------------------------------------
    print("\n[gate enforcement via approve_message API helpers]")
    # Mark good_msg with a failing check so approval should be blocked.
    # First remove suppression so we can craft a controlled scenario.
    # (suppression rule will keep failing for good_msg, which is what we want)
    from services.outreach_service import approve_message as _approve_helper
    # The service-level approve_message has no gate; the gate lives in the API.
    # Validate the API gate via TestClient.
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # gate: no quality check -> 400 quality_check_required for a fresh message
    fresh_msg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": _good_subject(), "body": _good_body(), "status": "draft",
    })
    r = client.post(f"/outreach/{fresh_msg}/approve", json={})
    assertion(r.status_code == 400 and r.json().get("detail") == "quality_check_required",
              f"no qc -> 400 quality_check_required (got {r.status_code} {r.text})", failures)

    # gate: failing latest qc -> 400 quality_check_failed
    # good_msg already has latest qc that failed (suppression).
    r = client.post(f"/outreach/{good_msg}/approve", json={})
    assertion(r.status_code == 400 and r.json().get("detail") == "quality_check_failed",
              f"failing qc -> 400 quality_check_failed (got {r.status_code} {r.text})", failures)

    # gate: force=true bypasses
    r = client.post(f"/outreach/{good_msg}/approve", json={"force": True})
    assertion(r.status_code == 200 and r.json().get("status") == "approved",
              f"force=true approves (got {r.status_code} {r.text})", failures)
    assertion(r.json().get("forced") is True, "forced flag echoed", failures)

    # gate: passing qc -> approve succeeds without force
    # remove suppression entry, then re-check fresh_msg
    sup_row = repos.suppression.find_one({
        "suppression_type": "email", "value": "alex@acmeco14.example",
    })
    if sup_row:
        repos.suppression.delete(int(sup_row["id"]))
    quality_check_for_message(repos, fresh_msg)  # should pass now
    r = client.post(f"/outreach/{fresh_msg}/approve", json={})
    assertion(r.status_code == 200 and r.json().get("status") == "approved",
              f"passing qc approves (got {r.status_code} {r.text})", failures)

    # ------------------------------------------------------------------
    print("\n[404 paths]")
    r404 = quality_check_for_message(repos, 999999)
    assertion(not r404["ok"] and r404["error"] == "message_not_found",
              "missing message", failures)
    r = client.post("/outreach/999999/quality-check", json={})
    assertion(r.status_code == 404, f"404 quality-check (got {r.status_code})", failures)
    r = client.get("/outreach/999999/quality")
    assertion(r.status_code == 404, f"404 GET quality (got {r.status_code})", failures)

    # ------------------------------------------------------------------
    print("\n[400 paths]")
    r = client.post("/quality/run", json={})
    assertion(r.status_code == 400, f"400 no identifier (got {r.status_code})", failures)
    r = client.post("/quality/run", json={"project_id": pid, "only_status": ["nope"]})
    assertion(r.status_code == 400, f"400 bad only_status (got {r.status_code})", failures)

    # ------------------------------------------------------------------
    print("\n[batch run]")
    batch = run_quality_batch(repos, project_id=pid, only_missing=False, limit=50)
    # good_msg + fresh_msg are now status=approved after the gate test;
    # bad_subject_msg + merge_msg + spam_msg remain status=draft.
    assertion(batch["scanned"] >= 3, f"scanned >= 3 ({batch['scanned']})", failures)
    assertion(batch["checked"] == batch["scanned"], "checked == scanned", failures)

    # ------------------------------------------------------------------
    print("\n[GET /quality list]")
    r = client.get(f"/quality?project_id={pid}&limit=50")
    assertion(r.status_code == 200, f"GET /quality 200 (got {r.status_code})", failures)
    data = r.json()
    assertion(data["count"] >= 1, f"count >= 1 ({data['count']})", failures)
    assertion(isinstance(data["data"][0].get("rule_results"), list),
              "rule_results decoded as list", failures)

    # ------------------------------------------------------------------
    print("\n[taxonomy guard]")
    assertion("draft" in OUTREACH_STATUSES, "OUTREACH_STATUSES intact", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=quality_control]")
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="quality_control",
        config={"only_missing": False, "limit": 50},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

    # ------------------------------------------------------------------
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
