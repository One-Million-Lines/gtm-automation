"""Suppression service.

Responsibilities:
  - Normalize raw suppression entries (per type).
  - Bulk-import lists/CSV-style records.
  - Apply suppression to lead_candidates: set lead_status='suppressed' for any
    lead whose company.domain / company.name / contact.email / contact.linkedin_url
    matches a suppression entry.

Suppression types:
  domain | email | company_name | linkedin_url | competitor | customer
  | unsubscribed | bounced
"""
from __future__ import annotations

from typing import Any, Iterable

from services.company_discovery_service import normalize_domain


VALID_TYPES = {
    "domain", "email", "company_name", "linkedin_url",
    "competitor", "customer", "unsubscribed", "bounced",
}

# Types that match against company.domain
_DOMAIN_TYPES = {"domain", "competitor", "customer"}
# Types that match against company.name (case-insensitive)
_COMPANY_NAME_TYPES = {"company_name"}
# Types that match against contact.email
_EMAIL_TYPES = {"email", "unsubscribed", "bounced"}
# Types that match against contact.linkedin_url
_LINKEDIN_TYPES = {"linkedin_url"}


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def normalize_value(suppression_type: str, value: Any) -> str | None:
    """Normalize a raw suppression value depending on type. Returns None if invalid."""
    if suppression_type not in VALID_TYPES:
        return None
    s = _str_or_none(value)
    if not s:
        return None
    if suppression_type in _DOMAIN_TYPES:
        return normalize_domain(s)
    if suppression_type in _EMAIL_TYPES:
        s = s.lower()
        if "@" not in s or "." not in s.split("@", 1)[-1]:
            return None
        return s
    if suppression_type in _LINKEDIN_TYPES:
        return s.lower().rstrip("/")
    if suppression_type in _COMPANY_NAME_TYPES:
        return s.lower()
    return s


def normalize_record(raw: dict) -> dict | None:
    stype = _str_or_none(raw.get("suppression_type"))
    if not stype or stype not in VALID_TYPES:
        return None
    value = normalize_value(stype, raw.get("value"))
    if not value:
        return None
    return {
        "suppression_type": stype,
        "value": value,
        "reason": _str_or_none(raw.get("reason")),
        "source": _str_or_none(raw.get("source")),
    }


def ingest_records(repos, records: Iterable[dict]) -> dict:
    """Normalize then bulk-add. Returns counts."""
    cleaned: list[dict] = []
    invalid = 0
    for r in records or []:
        if not isinstance(r, dict):
            invalid += 1
            continue
        norm = normalize_record(r)
        if not norm:
            invalid += 1
            continue
        cleaned.append(norm)
    summary = repos.suppression.bulk_add(cleaned)
    summary["input"] = sum(1 for _ in records) if hasattr(records, "__len__") else len(cleaned) + invalid
    summary["invalid"] = invalid
    return summary


# ---------------------------------------------------------------------------
# Apply suppression to leads
# ---------------------------------------------------------------------------
def _domain_set(by_type: dict[str, set[str]]) -> set[str]:
    out: set[str] = set()
    for t in _DOMAIN_TYPES:
        out |= by_type.get(t, set())
    return out


def _email_set(by_type: dict[str, set[str]]) -> set[str]:
    out: set[str] = set()
    for t in _EMAIL_TYPES:
        out |= by_type.get(t, set())
    return out


def apply_suppression_to_leads(
    repos,
    *,
    project_id: int | None = None,
    icp_id: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Scan lead_candidates (project/icp scoped or all-active) and mark any
    matching lead as lead_status='suppressed' with rejection_reason='suppressed: <type>'.

    Returns: {scanned, suppressed, by_reason, lead_ids[:50]}
    """
    by_type = repos.suppression.values_by_type()
    domain_values = _domain_set(by_type)
    email_values = _email_set(by_type)
    name_values = by_type.get("company_name", set())
    linkedin_values = by_type.get("linkedin_url", set())

    # Find candidate leads: skip already-suppressed/rejected/exported.
    sql = (
        "SELECT lc.id AS lead_id, lc.lead_status, "
        "       co.id AS company_id, co.domain AS company_domain, co.name AS company_name, "
        "       ct.id AS contact_id, ct.email AS contact_email, ct.linkedin_url AS contact_linkedin "
        "FROM lead_candidates lc "
        "JOIN companies co ON co.id = lc.company_id "
        "LEFT JOIN contacts ct ON ct.id = lc.contact_id "
        "WHERE lc.lead_status NOT IN ('suppressed','rejected','exported','contacted','replied') "
    )
    params: list[Any] = []
    if project_id is not None:
        sql += " AND lc.project_id = ?"
        params.append(int(project_id))
    if icp_id is not None:
        sql += " AND lc.icp_id = ?"
        params.append(int(icp_id))
    rows = repos.suppression.storage.fetchall(sql, tuple(params))

    suppressed_ids: list[int] = []
    by_reason: dict[str, int] = {}

    for row in rows:
        reason: str | None = None
        cd = (row.get("company_domain") or "").lower() or None
        cn = (row.get("company_name") or "").lower() or None
        em = (row.get("contact_email") or "").lower() or None
        ln = (row.get("contact_linkedin") or "").lower().rstrip("/") or None

        if cd and cd in domain_values:
            reason = "domain"
        elif em and em in email_values:
            reason = "email"
        elif ln and ln in linkedin_values:
            reason = "linkedin_url"
        elif cn and cn in name_values:
            reason = "company_name"

        if not reason:
            continue
        suppressed_ids.append(int(row["lead_id"]))
        by_reason[reason] = by_reason.get(reason, 0) + 1

        if not dry_run:
            repos.lead_candidates.update(
                int(row["lead_id"]),
                {
                    "lead_status": "suppressed",
                    "rejection_reason": f"suppressed: {reason}",
                    "ready_for_outreach": 0,
                },
            )

    return {
        "scanned": len(rows),
        "suppressed": len(suppressed_ids),
        "by_reason": by_reason,
        "lead_ids": suppressed_ids[:50],
        "dry_run": dry_run,
    }
