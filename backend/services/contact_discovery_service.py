"""Contact discovery service.

Mirrors company_discovery_service: pure-ish helpers + ingest_record + ingest_records.

Dedupe order for contacts: email (lowercased) -> linkedin_url -> (company_id, full_name lower).
After upsert, links the contact into lead_candidates via LeadCandidateRepo.upsert_full,
which attaches to a placeholder (icp_id, company_id, NULL) row when present.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from services.company_discovery_service import normalize_domain
from services.role_matcher import match_role


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _norm_email(v: Any) -> str | None:
    s = _str_or_none(v)
    if not s:
        return None
    s = s.lower()
    return s if _EMAIL_RE.match(s) else None


def _norm_full_name(first: str | None, last: str | None, full: str | None) -> str | None:
    if full and full.strip():
        return " ".join(full.split())
    parts = [p for p in (first, last) if p and p.strip()]
    return " ".join(parts) if parts else None


def normalize_contact(raw: dict, *, company_id: int | None = None) -> dict:
    """Build a normalized contact payload from a raw dict.

    Does NOT enforce that company_id is set — caller is responsible for resolving
    company_id (from raw 'company_id' or 'company_domain').
    """
    first = _str_or_none(raw.get("first_name"))
    last = _str_or_none(raw.get("last_name"))
    full = _norm_full_name(first, last, _str_or_none(raw.get("full_name")))
    email = _norm_email(raw.get("email"))
    linkedin = _str_or_none(raw.get("linkedin_url"))

    payload: dict = {
        "company_id": company_id,
        "first_name": first,
        "last_name": last,
        "full_name": full,
        "job_title": _str_or_none(raw.get("job_title")),
        "email": email,
        "email_status": _str_or_none(raw.get("email_status")),
        "email_confidence": raw.get("email_confidence"),
        "linkedin_url": linkedin,
        "country": _str_or_none(raw.get("country")),
        "city": _str_or_none(raw.get("city")),
    }
    return {k: v for k, v in payload.items() if v is not None}


def merge_contact_payload(existing: dict, new: dict) -> dict:
    """Merge two contact payloads. Prefer existing non-empty values; only fill
    blanks from new. Always overwrite job_title / normalized_role / email_status /
    email_confidence with new when new provides a non-empty value."""
    out = dict(existing)
    overwrite_keys = {"job_title", "normalized_role", "email_status",
                      "email_confidence", "country", "city"}
    for k, v in new.items():
        if v in (None, "", []):
            continue
        if k in overwrite_keys or not existing.get(k):
            out[k] = v
    return out


def _has_identity(payload: dict) -> bool:
    return bool(
        payload.get("email")
        or payload.get("linkedin_url")
        or payload.get("full_name")
    )


def ingest_contact_record(
    repos,
    *,
    project_id: int,
    icp_id: int,
    company_id: int,
    source_name: str,
    raw: dict,
    source_type: str | None = None,
    target_personas: list[str] | None = None,
) -> dict:
    """Ingest a single contact for a known company. Returns:
        {contact_id, source_id, action, lead_id, lead_action, role, reason?}
    where action in {created, updated, skipped} and lead_action in {created, updated, attached, none}.
    """
    payload = normalize_contact(raw, company_id=company_id)
    if not _has_identity(payload):
        return {"action": "skipped", "reason": "missing email/linkedin/full_name",
                "contact_id": None, "source_id": None, "lead_id": None,
                "lead_action": "none", "role": None}

    # Suppression check (email).
    if payload.get("email") and repos.suppression.is_suppressed("email", payload["email"]):
        return {"action": "skipped", "reason": "email suppressed",
                "contact_id": None, "source_id": None, "lead_id": None,
                "lead_action": "none", "role": None}

    # Role matching — drives normalized_role.
    role = match_role(payload.get("job_title"), target_personas)
    if role.get("normalized_role"):
        payload["normalized_role"] = role["normalized_role"]

    # Find existing for merge BEFORE upsert.
    existing = None
    if payload.get("email"):
        existing = repos.contacts.get_by_email(payload["email"])
    if not existing and payload.get("linkedin_url"):
        existing = repos.contacts.get_by_linkedin(payload["linkedin_url"])
    if not existing and payload.get("full_name"):
        existing = repos.contacts.get_by_company_and_name(
            company_id, payload["full_name"].strip().lower()
        )

    if existing:
        merged = merge_contact_payload(existing, payload)
        # Keep the original company_id when merging (don't reassign).
        merged["company_id"] = existing["company_id"]
        repos.contacts.update(int(existing["id"]), merged)
        contact_id = int(existing["id"])
        action = "updated"
    else:
        contact_id = repos.contacts.create(payload)
        action = "created"

    # Always record a contact_sources row.
    source_id = repos.contact_sources.create({
        "contact_id": contact_id,
        "source_type": source_type or source_name,
        "source_name": source_name,
        "source_url": _str_or_none(raw.get("source_url")),
        "raw_data": raw,
        "confidence_score": role.get("confidence"),
    })

    # Wire into lead_candidates: attach to placeholder if present, else create.
    lead_id, lead_action = repos.lead_candidates.upsert_full(
        icp_id=icp_id,
        company_id=company_id,
        contact_id=contact_id,
        data={"project_id": project_id, "lead_status": "new"},
    )

    return {
        "action": action,
        "contact_id": contact_id,
        "source_id": source_id,
        "lead_id": lead_id,
        "lead_action": lead_action,
        "role": role,
    }


def ingest_contact_records(
    repos,
    *,
    project_id: int,
    icp_id: int,
    source_name: str,
    source_type: str | None,
    records: list[dict],
    company_resolver: Callable[[dict], int | None] | None = None,
    target_personas: list[str] | None = None,
) -> dict:
    """Batch ingest. company_resolver(raw) -> company_id | None.

    Default resolver: raw['company_id'] (int) or normalize_domain(raw['company_domain'])
    looked up via CompanyRepo.find_one({'domain': ...}).
    """
    if company_resolver is None:
        def _default_resolver(raw: dict) -> int | None:
            cid = raw.get("company_id")
            if cid:
                try:
                    return int(cid)
                except (TypeError, ValueError):
                    return None
            dom = normalize_domain(raw.get("company_domain") or raw.get("domain"))
            if not dom:
                return None
            row = repos.companies.find_one({"domain": dom})
            return int(row["id"]) if row else None
        company_resolver = _default_resolver

    summary: dict = {
        "input": len(records),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "skipped_details": [],
        "leads_created": 0,
        "leads_updated": 0,
        "leads_attached": 0,
    }

    for raw in records:
        company_id = company_resolver(raw)
        if not company_id:
            summary["skipped"] += 1
            summary["skipped_details"].append(
                {"reason": "unknown company", "record": raw}
            )
            continue
        result = ingest_contact_record(
            repos,
            project_id=project_id,
            icp_id=icp_id,
            company_id=company_id,
            source_name=source_name,
            source_type=source_type,
            raw=raw,
            target_personas=target_personas,
        )
        action = result.get("action")
        if action == "created":
            summary["created"] += 1
        elif action == "updated":
            summary["updated"] += 1
        else:
            summary["skipped"] += 1
            summary["skipped_details"].append(
                {"reason": result.get("reason") or "skipped", "record": raw}
            )
            continue
        la = result.get("lead_action")
        if la == "created":
            summary["leads_created"] += 1
        elif la == "updated":
            summary["leads_updated"] += 1
        elif la == "attached":
            summary["leads_attached"] += 1

    return summary
