"""Company discovery service — domain normalization, merge, ingestion."""
from __future__ import annotations

import re
from typing import Any

from repositories import RepoRegistry


_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$"
)


def normalize_domain(value: str | None) -> str | None:
    """Lowercase, strip protocol/www/path, validate basic shape. Returns None if invalid."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s:
        return None
    # Strip scheme
    if "://" in s:
        s = s.split("://", 1)[1]
    # Strip user@host
    if "@" in s and "." in s.split("@", 1)[1]:
        s = s.split("@", 1)[1]
    # Strip path / query / fragment
    for ch in ("/", "?", "#"):
        if ch in s:
            s = s.split(ch, 1)[0]
    # Strip port
    if ":" in s:
        s = s.split(":", 1)[0]
    # Strip leading www.
    if s.startswith("www."):
        s = s[4:]
    s = s.strip(".")
    if not s or "." not in s:
        return None
    if not _DOMAIN_RE.match(s):
        return None
    return s


_PREFER_NEW = {"updated_at"}
_KEEP_OLDEST = {"created_at"}


def merge_company_payload(existing: dict, new: dict) -> dict:
    """Prefer non-empty values, union tech_stack, keep oldest created_at."""
    out = dict(existing or {})
    for k, v in (new or {}).items():
        if k in _KEEP_OLDEST:
            continue
        if k == "tech_stack":
            cur = existing.get("tech_stack") or []
            inc = v or []
            if not isinstance(cur, list):
                cur = [cur]
            if not isinstance(inc, list):
                inc = [inc]
            seen: set[str] = set()
            merged: list[str] = []
            for item in [*cur, *inc]:
                key = str(item).strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(item)
            out["tech_stack"] = merged
            continue
        if v is None or v == "" or v == []:
            continue
        out[k] = v
    return out


_RECORD_FIELDS = (
    "name", "domain", "website_url", "linkedin_url", "country", "city",
    "industry", "description", "employee_count", "revenue_estimate",
    "ecommerce_platform", "tech_stack", "status",
)


def _extract_company_fields(raw: dict) -> dict:
    out: dict = {}
    for k in _RECORD_FIELDS:
        if k in raw and raw[k] not in (None, ""):
            out[k] = raw[k]
    return out


def ingest_company_record(
    repos: RepoRegistry,
    *,
    project_id: int,
    icp_id: int | None,
    source_name: str,
    raw: dict,
    source_type: str | None = None,
) -> dict:
    """Validate, upsert company by domain, write company_sources row, link lead candidate.

    Returns {company_id, source_id, action: 'created'|'updated'|'skipped', reason?}.
    """
    if not isinstance(raw, dict):
        return {"company_id": None, "source_id": None, "action": "skipped",
                "reason": "record is not a dict"}

    payload = _extract_company_fields(raw)

    # Domain may be on .domain or .website_url
    domain = normalize_domain(payload.get("domain")) or normalize_domain(payload.get("website_url"))
    has_name = bool(payload.get("name"))
    has_website = bool(payload.get("website_url") or payload.get("domain"))

    if not domain and not (has_name and has_website):
        return {"company_id": None, "source_id": None, "action": "skipped",
                "reason": "missing domain and (name+website)"}
    if not domain:
        return {"company_id": None, "source_id": None, "action": "skipped",
                "reason": "could not derive domain"}

    payload["domain"] = domain
    if not payload.get("website_url"):
        payload["website_url"] = f"https://{domain}"

    existing = repos.companies.find_one({"domain": domain})
    if existing:
        merged = merge_company_payload(existing, payload)
        # Strip immutable fields the upsert path doesn't need
        merged.pop("id", None)
        merged.pop("created_at", None)
        company_id = repos.companies.upsert_by_domain(merged)
        action = "updated"
    else:
        company_id = repos.companies.upsert_by_domain(payload)
        action = "created"

    source_id = repos.company_sources.create({
        "company_id": company_id,
        "source_type": source_type or source_name,
        "source_name": source_name,
        "source_url": raw.get("source_url") or raw.get("source") or None,
        "raw_data": raw,
        "confidence_score": raw.get("confidence_score"),
    })

    # Link lead candidate (no contact yet)
    if icp_id is not None:
        repos.lead_candidates.upsert(
            icp_id=int(icp_id),
            company_id=int(company_id),
            contact_id=None,
            data={"project_id": int(project_id)},
        )

    return {"company_id": int(company_id), "source_id": int(source_id), "action": action}


def ingest_records(
    repos: RepoRegistry,
    *,
    project_id: int,
    icp_id: int | None,
    source_name: str,
    records: list[dict],
    source_type: str | None = None,
) -> dict:
    """Run ingest_company_record for each record. Returns summary dict."""
    created = 0
    updated = 0
    skipped: list[dict] = []
    for rec in records or []:
        try:
            res = ingest_company_record(
                repos, project_id=project_id, icp_id=icp_id,
                source_name=source_name, raw=rec, source_type=source_type,
            )
        except Exception as e:  # noqa: BLE001
            skipped.append({"reason": f"exception: {e}", "record": rec})
            continue
        if res["action"] == "created":
            created += 1
        elif res["action"] == "updated":
            updated += 1
        else:
            skipped.append({"reason": res.get("reason", "skipped"), "record": rec})
    return {
        "input": len(records or []),
        "created": created,
        "updated": updated,
        "skipped": len(skipped),
        "skipped_details": skipped,
    }
