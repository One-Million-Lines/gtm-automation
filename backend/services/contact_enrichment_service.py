"""Contact enrichment service.

Validates a contact's email (syntax + free/disposable/role + MX), persists a
`contact_enrichment` snapshot, and merges new info back into the `contacts` row
(email_status, email_confidence, normalized_role if missing, email if typo-fixed).

Also offers a CSV-paste import path that upserts contacts (by email/linkedin/
company+name), enriches inline, and creates/updates lead_candidates.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable

from services.email_validator import (
    EmailValidator, ValidateResult,
    get_default_validator, normalize_email,
)
from services.role_matcher import match_role

PROVIDER = "email_validation"


# ---------------------------------------------------------------------------
# CSV parsing (header-aware)
# ---------------------------------------------------------------------------
ALLOWED_CSV_FIELDS = {
    "email", "first_name", "last_name", "full_name", "job_title",
    "email_status", "email_confidence", "linkedin_url",
    "company_id", "company_domain", "country", "city",
}


def parse_enriched_csv(text: str) -> list[dict[str, Any]]:
    """Parse a CSV string with a header row. Unknown columns are ignored.
    Empty values are dropped (not coerced to None to keep raw shape predictable).
    """
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for row in reader:
        rec: dict[str, Any] = {}
        for k, v in row.items():
            if not k:
                continue
            kk = k.strip().lower()
            if kk not in ALLOWED_CSV_FIELDS:
                continue
            if v is None:
                continue
            sv = str(v).strip()
            if sv == "":
                continue
            rec[kk] = sv
        if rec:
            rows.append(rec)
    return rows


# ---------------------------------------------------------------------------
# Snapshot builder (pure)
# ---------------------------------------------------------------------------
def build_snapshot(result: ValidateResult, *, source: str = "live") -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "source": source,                # "live" | "csv_import" | "pipeline"
        "email": result.normalized,
        "email_status": result.status,
        "email_confidence": result.confidence,
        "syntax_ok": result.syntax_ok,
        "domain": result.domain,
        "is_free": result.is_free,
        "is_disposable": result.is_disposable,
        "is_role": result.is_role,
        "has_mx": result.has_mx,
        "is_catch_all": result.is_catch_all,
        "typo_corrected_from": result.typo_corrected,
        "reason": result.reason,
        "raw": result.raw or {},
    }


def _merge_contact_updates(existing: dict, snapshot: dict, role_info: dict | None) -> dict:
    """Compute patch to apply to contacts row. Conservative — only fills blanks
    or overwrites status/confidence (which are the whole point)."""
    out: dict[str, Any] = {}
    new_status = snapshot.get("email_status")
    if new_status and new_status != existing.get("email_status"):
        out["email_status"] = new_status
    new_conf = snapshot.get("email_confidence")
    if new_conf is not None and new_conf != existing.get("email_confidence"):
        out["email_confidence"] = float(new_conf)
    # Apply typo-corrected email back into contacts.email when present and the
    # current email matches the typoed source.
    typo_from = snapshot.get("typo_corrected_from")
    new_email = snapshot.get("email")
    if typo_from and new_email and existing.get("email") != new_email:
        out["email"] = new_email
    # Normalized role: only fill if absent.
    if role_info and role_info.get("normalized_role") and not existing.get("normalized_role"):
        out["normalized_role"] = role_info["normalized_role"]
    # Mark contact status as enriched if it was 'new'/empty.
    if existing.get("status") in (None, "", "new"):
        out["status"] = "enriched"
    return out


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
def _persist_snapshot(repos, *, contact_id: int, contact: dict, snapshot: dict) -> int:
    return int(repos.contact_enrichment.create({
        "contact_id": contact_id,
        "provider": snapshot.get("provider") or PROVIDER,
        "email": snapshot.get("email") or contact.get("email"),
        "email_status": snapshot.get("email_status"),
        "email_confidence": snapshot.get("email_confidence"),
        "job_title": contact.get("job_title"),
        "linkedin_url": contact.get("linkedin_url"),
        "phone": None,
        "raw_data": snapshot,
    }))


# ---------------------------------------------------------------------------
# Single contact enrich
# ---------------------------------------------------------------------------
def enrich_contact(
    repos,
    *,
    contact_id: int,
    validator: EmailValidator | None = None,
    target_personas: list[str] | None = None,
    dry_run: bool = False,
    source: str = "live",
) -> dict[str, Any]:
    contact = repos.contacts.get(contact_id)
    if not contact:
        return {"contact_id": contact_id, "ok": False, "skipped": True,
                "error": "contact_not_found", "dry_run": dry_run}

    email = contact.get("email")
    if not email:
        return {"contact_id": contact_id, "ok": False, "skipped": True,
                "error": "contact_missing_email", "dry_run": dry_run}

    v = validator or get_default_validator()
    result = v.validate(email)
    snapshot = build_snapshot(result, source=source)

    role_info = None
    if not contact.get("normalized_role") and contact.get("job_title"):
        role_info = match_role(contact.get("job_title"), target_personas)

    updates = _merge_contact_updates(contact, snapshot, role_info)

    out: dict[str, Any] = {
        "contact_id": contact_id,
        "email": email,
        "ok": result.syntax_ok and result.status != "invalid",
        "status": snapshot["email_status"],
        "confidence": snapshot["email_confidence"],
        "snapshot": snapshot,
        "updates": updates,
        "dry_run": dry_run,
    }

    if dry_run:
        return out

    enrichment_id = _persist_snapshot(repos, contact_id=contact_id, contact=contact, snapshot=snapshot)
    out["enrichment_id"] = enrichment_id
    if updates:
        repos.contacts.update(contact_id, updates)
    return out


# ---------------------------------------------------------------------------
# Batch enrich
# ---------------------------------------------------------------------------
def _select_contact_ids(
    repos, *,
    project_id: int | None,
    company_id: int | None,
    contact_ids: list[int] | None,
    limit: int,
) -> list[int]:
    if contact_ids:
        return [int(x) for x in contact_ids][:limit]
    if company_id is not None:
        rows = repos.contacts.storage.fetchall(
            "SELECT id FROM contacts WHERE company_id = ? ORDER BY id ASC LIMIT ?",
            (int(company_id), int(limit)),
        )
        return [int(r["id"]) for r in rows]
    if project_id is not None:
        rows = repos.contacts.storage.fetchall(
            "SELECT DISTINCT c.id FROM contacts c "
            "JOIN lead_candidates lc ON lc.contact_id = c.id "
            "WHERE lc.project_id = ? "
            "ORDER BY c.id ASC LIMIT ?",
            (int(project_id), int(limit)),
        )
        return [int(r["id"]) for r in rows]
    rows = repos.contacts.storage.fetchall(
        "SELECT id FROM contacts ORDER BY id ASC LIMIT ?", (int(limit),),
    )
    return [int(r["id"]) for r in rows]


def enrich_contacts_batch(
    repos,
    *,
    project_id: int | None = None,
    company_id: int | None = None,
    contact_ids: list[int] | None = None,
    limit: int = 100,
    only_missing: bool = True,
    validator: EmailValidator | None = None,
    target_personas: list[str] | None = None,
    dry_run: bool = False,
    source: str = "pipeline",
) -> dict[str, Any]:
    ids = _select_contact_ids(
        repos, project_id=project_id, company_id=company_id,
        contact_ids=contact_ids, limit=limit,
    )
    results: list[dict] = []
    skipped = 0
    failed = 0
    for cid in ids:
        if only_missing and repos.contact_enrichment.exists({"contact_id": cid}):
            skipped += 1
            continue
        try:
            res = enrich_contact(
                repos, contact_id=cid, validator=validator,
                target_personas=target_personas, dry_run=dry_run, source=source,
            )
        except Exception as e:  # noqa: BLE001
            failed += 1
            results.append({"contact_id": cid, "ok": False, "error": str(e)})
            continue
        if res.get("skipped"):
            skipped += 1
        elif not res.get("ok"):
            failed += 1
        results.append(res)
    return {
        "scanned": len(ids),
        "enriched": sum(1 for r in results if r.get("ok") and not r.get("skipped")),
        "skipped": skipped,
        "failed": failed,
        "results": results,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# CSV import (upsert + enrich + lead_candidates)
# ---------------------------------------------------------------------------
def _resolve_company_id(repos, raw: dict) -> int | None:
    cid = raw.get("company_id")
    if cid:
        try:
            return int(cid)
        except (TypeError, ValueError):
            return None
    dom = raw.get("company_domain")
    if dom:
        from services.company_discovery_service import normalize_domain
        nd = normalize_domain(dom)
        if nd:
            row = repos.companies.find_one({"domain": nd})
            if row:
                return int(row["id"])
    # Fallback: derive from email domain.
    em = normalize_email(raw.get("email"))
    if em and "@" in em:
        edom = em.split("@", 1)[1]
        row = repos.companies.find_one({"domain": edom})
        if row:
            return int(row["id"])
    return None


def import_enriched_contacts(
    repos,
    *,
    project_id: int,
    icp_id: int,
    records: list[dict],
    source_name: str = "csv_import",
    validator: EmailValidator | None = None,
    target_personas: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert + enrich. Each record may have email, linkedin_url, names, role
    fields. Creates/attaches lead_candidates per upserted contact.
    """
    summary: dict[str, Any] = {
        "input": len(records),
        "created": 0, "updated": 0, "skipped": 0, "skipped_details": [],
        "enriched": 0, "leads_created": 0, "leads_updated": 0, "leads_attached": 0,
        "results": [],
    }

    for raw in records:
        email = normalize_email(raw.get("email"))
        linkedin = (raw.get("linkedin_url") or "").strip() or None
        full_name_parts = [raw.get("first_name"), raw.get("last_name")]
        full_name = " ".join([p for p in full_name_parts if p]) or None

        if not (email or linkedin or full_name):
            summary["skipped"] += 1
            summary["skipped_details"].append({"reason": "no_identity", "record": raw})
            continue

        company_id = _resolve_company_id(repos, raw)
        if not company_id:
            summary["skipped"] += 1
            summary["skipped_details"].append({"reason": "unknown_company", "record": raw})
            continue

        # Suppression early-out on email.
        if email and repos.suppression.is_suppressed("email", email):
            summary["skipped"] += 1
            summary["skipped_details"].append({"reason": "email_suppressed", "record": raw})
            continue

        payload: dict[str, Any] = {"company_id": company_id}
        if raw.get("first_name"): payload["first_name"] = raw["first_name"]
        if raw.get("last_name"):  payload["last_name"]  = raw["last_name"]
        if full_name:             payload["full_name"]  = full_name
        if raw.get("job_title"):  payload["job_title"]  = raw["job_title"]
        if email:                 payload["email"]      = email
        if linkedin:              payload["linkedin_url"] = linkedin
        if raw.get("country"):    payload["country"]    = raw["country"]
        if raw.get("city"):       payload["city"]       = raw["city"]
        # Caller-provided email status/confidence are accepted as priors but will
        # be overwritten by the validator unless they're "valid"+conf>=0.9.
        if raw.get("email_status"):
            payload["email_status"] = raw["email_status"]
        if raw.get("email_confidence") is not None:
            try:
                payload["email_confidence"] = float(raw["email_confidence"])
            except (TypeError, ValueError):
                pass

        # Role match.
        if payload.get("job_title"):
            r = match_role(payload["job_title"], target_personas)
            if r.get("normalized_role"):
                payload["normalized_role"] = r["normalized_role"]

        contact_id, action = repos.contacts.upsert_contact(payload)

        # Source row
        repos.contact_sources.create({
            "contact_id": contact_id,
            "source_type": source_name,
            "source_name": source_name,
            "source_url": None,
            "raw_data": raw,
            "confidence_score": payload.get("email_confidence"),
        })

        # Enrich inline
        enrich_res = enrich_contact(
            repos, contact_id=contact_id, validator=validator,
            target_personas=target_personas, dry_run=False, source="csv_import",
        )
        if enrich_res.get("ok") and not enrich_res.get("skipped"):
            summary["enriched"] += 1

        # Wire into lead_candidates
        lead_id, lead_action = repos.lead_candidates.upsert_full(
            icp_id=icp_id, company_id=company_id, contact_id=contact_id,
            data={"project_id": project_id, "lead_status": "new"},
        )

        if action == "created":
            summary["created"] += 1
        else:
            summary["updated"] += 1
        if lead_action == "created":
            summary["leads_created"] += 1
        elif lead_action == "updated":
            summary["leads_updated"] += 1
        elif lead_action == "attached":
            summary["leads_attached"] += 1

        summary["results"].append({
            "contact_id": contact_id, "action": action,
            "lead_id": lead_id, "lead_action": lead_action,
            "email_status": enrich_res.get("status"),
            "email_confidence": enrich_res.get("confidence"),
        })

    # Re-apply suppression once after import (covers any new email/linkedin/domain
    # that matches existing suppression rules).
    try:
        from services.suppression_service import apply_suppression_to_leads
        sup = apply_suppression_to_leads(repos, project_id=project_id, dry_run=False)
        summary["suppression_reapplied"] = {
            "scanned": sup.get("scanned"), "suppressed": sup.get("suppressed"),
        }
    except Exception as e:  # noqa: BLE001
        summary["suppression_reapplied"] = {"error": str(e)}

    return summary
