"""Smoke test for File 16 — reply tracking + auto-reply classification (no real network)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_shared import pipeline_runner, repos
from services.email_sender import FakeEmailSender, set_default_email_sender
from services.reply_classifier import (
    FakeReplyClassifier, LLMReplyClassifier, REPLY_INTENTS,
    RuleBasedReplyClassifier, classify_reply,
    get_default_reply_classifier, set_default_reply_classifier,
)
from services.reply_ingestor import (
    FakeReplyIngestor, WebhookReplyIngestor,
    get_default_reply_ingestor, set_default_reply_ingestor,
)
from services.reply_service import (
    AUTO_SUPPRESS_INTENTS, _match_send_for_reply, ingest_reply, run_reply_poll,
)
from services.send_service import send_for_message


def assertion(cond: bool, msg: str, failures: list) -> None:
    print(f"  {'OK ' if cond else 'XX '} {msg}")
    if not cond:
        failures.append(msg)


def main() -> int:
    failures: list[str] = []

    # ------------------------------------------------------------------
    print("\n[taxonomy]")
    assertion(
        set(REPLY_INTENTS) == {"positive", "negative", "oof", "unsubscribe", "info_request", "neutral"},
        "REPLY_INTENTS taxonomy", failures,
    )
    assertion(
        set(AUTO_SUPPRESS_INTENTS) == {"negative", "unsubscribe"},
        "AUTO_SUPPRESS_INTENTS", failures,
    )

    # ------------------------------------------------------------------
    print("\n[pluggable defaults reset]")
    set_default_reply_classifier(None)
    assertion(get_default_reply_classifier().name == "rule_based",
              "default classifier resets to rule_based", failures)
    set_default_reply_ingestor(None)
    assertion(get_default_reply_ingestor().name == "fake",
              "default ingestor resets to fake", failures)

    # ------------------------------------------------------------------
    print("\n[RuleBasedReplyClassifier fixtures]")
    rb = RuleBasedReplyClassifier()
    fixtures = {
        "positive": "Sounds great, let's chat next week.",
        "negative": "Not interested, please stop.",
        "oof": "I'm out of office until Monday.",
        "unsubscribe": "Please unsubscribe me from this list.",
        "info_request": "Can you tell me more about pricing?",
        "neutral": "Thanks.",
    }
    for expected, body in fixtures.items():
        r = rb.classify(body=body)
        assertion(r["intent"] == expected,
                  f"rule_based '{body[:30]}' -> {r['intent']} (want {expected})",
                  failures)

    # ------------------------------------------------------------------
    print("\n[LLMReplyClassifier(llm=None) -> rule_based fallback]")
    llmc = LLMReplyClassifier(llm=None)
    r = llmc.classify(body="Please unsubscribe me")
    assertion(r["intent"] == "unsubscribe",
              f"llm None falls back to rules ({r})", failures)
    assertion("fallback" in r["classifier"],
              f"classifier annotated as fallback ({r['classifier']})", failures)

    # ------------------------------------------------------------------
    print("\n[FakeReplyClassifier]")
    fc = FakeReplyClassifier(intent="positive", confidence=0.99)
    r = fc.classify(body="anything")
    assertion(r["intent"] == "positive" and r["confidence"] == 0.99,
              "fake classifier deterministic", failures)

    # ------------------------------------------------------------------
    print("\n[classify_reply convenience]")
    set_default_reply_classifier(FakeReplyClassifier(intent="oof"))
    r = classify_reply(body="hi")
    assertion(r["intent"] == "oof", f"convenience uses default ({r})", failures)
    set_default_reply_classifier(None)

    # ------------------------------------------------------------------
    print("\n[WebhookReplyIngestor field map]")
    wh = WebhookReplyIngestor()
    wh.add({
        "MessageID": "<webhook-1@x>",
        "InReplyTo": "<send-msg@x>",
        "From": "lead@example.com",
        "Subject": "Re: hi",
        "TextBody": "Sounds good",
    })
    items = wh.fetch()
    assertion(len(items) == 1 and items[0]["from_email"] == "lead@example.com"
              and items[0]["message_id_external"] == "<webhook-1@x>"
              and items[0]["body"] == "Sounds good",
              f"webhook normalize ({items})", failures)

    # ------------------------------------------------------------------
    print("\n[db scenario setup]")
    set_default_email_sender(FakeEmailSender())
    pid = repos.projects.create({"name": "smoke16"})
    icp_id = repos.icps.create({
        "project_id": pid, "name": "ICP1", "status": "draft",
        "target_industries": ["saas"], "target_roles": ["cto"],
    })
    co = repos.companies.create({
        "name": "AcmeCo", "domain": "acmeco16.example", "industry": "saas",
        "status": "discovered",
    })
    ct = repos.contacts.create({
        "company_id": co, "first_name": "Alex", "last_name": "X", "full_name": "Alex X",
        "job_title": "CTO", "email": "alex@acmeco16.example", "status": "new",
    })
    lead = repos.lead_candidates.create({
        "project_id": pid, "icp_id": icp_id,
        "company_id": co, "contact_id": ct, "lead_status": "scored",
        "priority_tier": "A", "final_score": 0.95,
    })
    msg_id = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email",
        "subject": "Quick thought", "body": "Hi Alex, " + " ".join(["w"] * 80),
        "status": "approved", "approved_at": "2025-01-01T00:00:00",
    })
    sent = send_for_message(repos, msg_id)
    assertion(sent.get("ok") and sent.get("send_id"), f"seed send ok ({sent})", failures)
    send_id = sent["send_id"]
    external_id = sent["message_id_external"]

    # ------------------------------------------------------------------
    print("\n[_match_send_for_reply]")
    matched = _match_send_for_reply(repos, in_reply_to=external_id, message_id_external=None)
    assertion(matched and int(matched["id"]) == int(send_id),
              f"match by in_reply_to ({matched})", failures)
    none_match = _match_send_for_reply(repos, in_reply_to="bogus", message_id_external="bogus")
    assertion(none_match is None, "no match on bogus", failures)

    # ------------------------------------------------------------------
    print("\n[ingest_reply positive]")
    r = ingest_reply(repos, {
        "provider": "fake",
        "message_id_external": "<r-pos@x>",
        "in_reply_to": external_id,
        "from_email": "alex@acmeco16.example",
        "subject": "Re: Quick thought",
        "body": "Sounds great, let's chat.",
        "received_at": "2025-01-02T00:00:00",
        "raw_response": {"src": "test"},
    }, classifier=RuleBasedReplyClassifier())
    assertion(r["ok"] and r["intent"] == "positive" and not r["suppressed"],
              f"positive ingest ({r})", failures)
    assertion(int(r["outreach_send_id"]) == int(send_id),
              "linked to outreach_send", failures)

    # ------------------------------------------------------------------
    print("\n[ingest_reply unsubscribe -> auto-suppress + send.status='replied']")
    r = ingest_reply(repos, {
        "provider": "fake",
        "message_id_external": "<r-unsub@x>",
        "in_reply_to": external_id,
        "from_email": "alex@acmeco16.example",
        "subject": "unsubscribe",
        "body": "Please unsubscribe me from this list.",
        "received_at": "2025-01-03T00:00:00",
        "raw_response": {},
    }, classifier=RuleBasedReplyClassifier())
    assertion(r["ok"] and r["intent"] == "unsubscribe" and r["suppressed"],
              f"unsubscribe suppressed ({r})", failures)
    assertion(repos.suppression.is_suppressed("email", "alex@acmeco16.example"),
              "suppression row exists", failures)
    send_after = repos.outreach_sends.get(int(send_id))
    assertion((send_after.get("status") or "") == "replied",
              f"send.status -> replied ({send_after.get('status')})", failures)

    # ------------------------------------------------------------------
    print("\n[ingest_reply negative -> auto-suppress]")
    # New send so it's still 'sent' before reply
    msg_neg = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email", "subject": "Re2",
        "body": "Hi " + " ".join(["w"] * 80), "status": "approved",
        "approved_at": "2025-01-04T00:00:00",
    })
    sent_neg = send_for_message(repos, msg_neg)
    r = ingest_reply(repos, {
        "provider": "fake",
        "message_id_external": "<r-neg@x>",
        "in_reply_to": sent_neg["message_id_external"],
        "from_email": "neg@acmeco16.example",
        "subject": "no",
        "body": "Not interested, please stop.",
        "raw_response": {},
    })
    assertion(r["ok"] and r["intent"] == "negative" and r["suppressed"],
              f"negative suppressed ({r})", failures)

    # ------------------------------------------------------------------
    print("\n[ingest_reply unmatched -> 400 path / no_matching_message]")
    r = ingest_reply(repos, {
        "provider": "fake", "in_reply_to": "<bogus@x>",
        "from_email": "x@y.com", "subject": "hi", "body": "hi",
    })
    assertion(not r.get("ok") and r.get("error") == "no_matching_message",
              f"unmatched -> error ({r})", failures)

    # ------------------------------------------------------------------
    print("\n[FK SET NULL: delete outreach_send -> reply.outreach_send_id NULL]")
    # Insert a third send + reply
    msg_fk = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email", "subject": "fk-test",
        "body": "Hi " + " ".join(["w"] * 80), "status": "approved",
        "approved_at": "2025-01-05T00:00:00",
    })
    sent_fk = send_for_message(repos, msg_fk)
    r = ingest_reply(repos, {
        "provider": "fake",
        "message_id_external": "<r-fk@x>",
        "in_reply_to": sent_fk["message_id_external"],
        "from_email": "fk@acmeco16.example",
        "subject": "Re: fk", "body": "Thanks.",
        "raw_response": {},
    })
    fk_reply_id = r["reply_id"]
    fk_send_id = sent_fk["send_id"]
    repos.outreach_sends.delete(int(fk_send_id))
    fk_reply_after = repos.outreach_replies.get(int(fk_reply_id))
    assertion(fk_reply_after is not None and fk_reply_after.get("outreach_send_id") is None,
              f"FK SET NULL after delete ({fk_reply_after.get('outreach_send_id')})",
              failures)

    # ------------------------------------------------------------------
    print("\n[run_reply_poll via FakeReplyIngestor]")
    set_default_email_sender(FakeEmailSender())
    msg_poll = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email", "subject": "poll-test",
        "body": "Hi " + " ".join(["w"] * 80), "status": "approved",
        "approved_at": "2025-01-06T00:00:00",
    })
    sent_poll = send_for_message(repos, msg_poll)
    ing = FakeReplyIngestor.from_sends(
        [{"id": sent_poll["send_id"],
          "message_id_external": sent_poll["message_id_external"]}],
        body="Sounds good, let's chat.",
        from_email="poll@acmeco16.example",
    )
    set_default_reply_ingestor(ing)
    result = run_reply_poll(repos, project_id=pid, classifier=RuleBasedReplyClassifier())
    assertion(result["scanned"] == 1 and result["ingested"] == 1,
              f"poll scanned/ingested ({result})", failures)
    assertion(result["by_intent"]["positive"] == 1,
              f"by_intent positive=1 ({result['by_intent']})", failures)
    set_default_reply_ingestor(None)

    # ------------------------------------------------------------------
    print("\n[OutreachReplyRepo.list_for_project]")
    rows = repos.outreach_replies.list_for_project(pid, limit=100)
    assertion(len(rows) >= 3, f"replies for project ({len(rows)})", failures)
    rows_unsub = repos.outreach_replies.list_for_project(pid, intent="unsubscribe", limit=10)
    assertion(any(r["intent"] == "unsubscribe" for r in rows_unsub),
              f"intent filter unsubscribe ({len(rows_unsub)})", failures)

    # ------------------------------------------------------------------
    print("\n[API: TestClient]")
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # Prepare a fresh send + ingestor for poll route
    msg_api = repos.outreach_messages.create({
        "lead_id": lead, "channel": "email", "subject": "api-test",
        "body": "Hi " + " ".join(["w"] * 80), "status": "approved",
        "approved_at": "2025-01-07T00:00:00",
    })
    sent_api = send_for_message(repos, msg_api)

    # POST /replies/ingest
    r = client.post("/replies/ingest", json={
        "provider": "fake",
        "message_id_external": "<api-r-1@x>",
        "in_reply_to": sent_api["message_id_external"],
        "from_email": "api@acmeco16.example",
        "subject": "Re: api-test",
        "body": "Sounds good.",
    })
    assertion(r.status_code == 200 and r.json().get("ok") and r.json().get("intent") == "positive",
              f"POST /replies/ingest ({r.status_code} {r.text})", failures)

    # POST /replies/ingest with unmatched -> 400
    r = client.post("/replies/ingest", json={
        "provider": "fake", "in_reply_to": "<bogus@x>", "body": "hi",
    })
    assertion(r.status_code == 400, f"unmatched -> 400 ({r.status_code})", failures)

    # POST /replies/ingest empty -> 400
    r = client.post("/replies/ingest", json={})
    assertion(r.status_code == 400, f"empty payload 400 ({r.status_code})", failures)

    # GET /outreach/{id}/replies
    r = client.get(f"/outreach/{msg_api}/replies")
    assertion(r.status_code == 200 and r.json().get("count") >= 1,
              f"GET outreach replies ({r.status_code} {r.text})", failures)

    # GET /outreach/999999/replies -> 404
    r = client.get("/outreach/999999/replies")
    assertion(r.status_code == 404, f"missing message 404 ({r.status_code})", failures)

    # POST /replies/poll (empty ingestor)
    set_default_reply_ingestor(FakeReplyIngestor())
    r = client.post("/replies/poll", json={"project_id": pid, "limit": 50})
    assertion(r.status_code == 200, f"POST /replies/poll ({r.status_code})", failures)
    assertion(r.json().get("scanned") == 0, f"empty poll scanned=0 ({r.json()})", failures)
    set_default_reply_ingestor(None)

    # GET /replies?intent=unsubscribe
    r = client.get(f"/replies?project_id={pid}&intent=unsubscribe")
    assertion(r.status_code == 200 and r.json().get("count") >= 1,
              f"GET /replies intent=unsubscribe ({r.status_code} {r.text})", failures)

    # GET /replies bad intent -> 400
    r = client.get(f"/replies?project_id={pid}&intent=bogus")
    assertion(r.status_code == 400, f"bad intent -> 400 ({r.status_code})", failures)

    # GET /replies/{id}
    rid = repos.outreach_replies.history_for_message(msg_api, limit=1)[0]["id"]
    r = client.get(f"/replies/{rid}")
    assertion(r.status_code == 200 and r.json().get("reply", {}).get("id") == rid,
              f"GET /replies/{{id}} ({r.status_code})", failures)

    # GET /replies/999999 -> 404
    r = client.get("/replies/999999")
    assertion(r.status_code == 404, f"missing reply 404 ({r.status_code})", failures)

    # ------------------------------------------------------------------
    print("\n[pipeline run_type=reply_tracking]")
    set_default_reply_ingestor(FakeReplyIngestor())
    run_id = pipeline_runner.run_now(
        project_id=pid, icp_id=icp_id, run_type="reply_tracking",
        config={"limit": 50},
    )
    detail = pipeline_runner.get_run_detail(run_id)
    run = detail.get("run") if isinstance(detail, dict) else None
    status = (run or {}).get("status") or detail.get("status")
    assertion(status == "completed", f"run completed -> {status}", failures)

    # ------------------------------------------------------------------
    set_default_email_sender(None)
    set_default_reply_ingestor(None)
    set_default_reply_classifier(None)

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
