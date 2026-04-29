"""ICP service — validation, normalization, CRUD orchestration, dashboard summary."""
from __future__ import annotations

from typing import Any

from repositories import RepoRegistry


# Field name aliases accepted by the API (spec uses target_* prefix; storage
# columns vary). All mappings are bidirectional via these constants.
_ALIASES = {
    "target_buying_signals": "buying_signals",
    "exclusion_criteria": "exclusion_rules",
}

# JSON list fields that should be lowercased + deduplicated when normalizing.
_LIST_FIELDS_LC = (
    "target_industries", "target_roles", "target_geographies", "target_seniorities",
)
# JSON list fields that should be deduplicated but not lowercased.
_LIST_FIELDS_RAW = (
    "target_personas", "target_company_sizes", "buying_signals",
    "pain_points", "competitors",
)

ALLOWED_SENIORITIES = {
    "junior", "mid", "senior", "lead", "manager", "director", "vp", "c_level",
}


def _apply_aliases(data: dict) -> dict:
    out = dict(data)
    for alias, real in _ALIASES.items():
        if alias in out and real not in out:
            out[real] = out.pop(alias)
    return out


def _norm_list(v: Any, lowercase: bool) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        items = [s for s in (x.strip() for x in v.split(",")) if s]
    elif isinstance(v, (list, tuple)):
        items = [str(x).strip() for x in v if str(x).strip()]
    else:
        raise ValueError(f"expected list or comma string, got {type(v).__name__}")
    if lowercase:
        items = [i.lower() for i in items]
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        key = i.lower()
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out


def normalize_icp_payload(data: dict, *, is_create: bool = False) -> dict:
    """Strip whitespace, dedupe + lowercase list fields, coerce ints, default status."""
    payload = _apply_aliases(data)
    out: dict = {}

    if "name" in payload and isinstance(payload["name"], str):
        out["name"] = payload["name"].strip()
    elif "name" in payload:
        out["name"] = payload["name"]

    for k in ("description", "offer_summary", "value_proposition", "outreach_angle",
              "target_revenue_range"):
        if k in payload and payload[k] is not None:
            out[k] = str(payload[k]).strip() or None

    for k in _LIST_FIELDS_LC:
        if k in payload:
            out[k] = _norm_list(payload[k], lowercase=True)
    for k in _LIST_FIELDS_RAW:
        if k in payload:
            out[k] = _norm_list(payload[k], lowercase=False)

    # exclusion_rules: accept dict, list, or string -> wrap into {raw: ...}
    if "exclusion_rules" in payload:
        v = payload["exclusion_rules"]
        if isinstance(v, str):
            out["exclusion_rules"] = {"raw": v.strip()} if v.strip() else None
        else:
            out["exclusion_rules"] = v

    for k in ("target_company_size_min", "target_company_size_max", "project_id"):
        if k in payload and payload[k] is not None and payload[k] != "":
            out[k] = int(payload[k])
        elif k in payload:
            out[k] = None

    if "status" in payload:
        out["status"] = payload["status"]
    elif is_create:
        out["status"] = "draft"

    return out


def validate_icp_payload(data: dict) -> None:
    """Raise ValueError on invalid create/update payload (post-normalization)."""
    if "name" in data:
        if not data.get("name") or not isinstance(data["name"], str):
            raise ValueError("name is required")

    if "target_industries" in data:
        if not isinstance(data["target_industries"], list) or not data["target_industries"]:
            raise ValueError("target_industries must be a non-empty list")

    if "target_roles" in data:
        if not isinstance(data["target_roles"], list) or not data["target_roles"]:
            raise ValueError("target_roles must be a non-empty list")

    if "target_geographies" in data:
        if not isinstance(data["target_geographies"], list):
            raise ValueError("target_geographies must be a list")

    if "target_seniorities" in data and data["target_seniorities"]:
        bad = [s for s in data["target_seniorities"] if s not in ALLOWED_SENIORITIES]
        if bad:
            raise ValueError(f"invalid seniorities: {bad}")

    mn = data.get("target_company_size_min")
    mx = data.get("target_company_size_max")
    if mn is not None and mn < 0:
        raise ValueError("target_company_size_min must be >= 0")
    if mx is not None and mx < 0:
        raise ValueError("target_company_size_max must be >= 0")
    if mn is not None and mx is not None and mn > mx:
        raise ValueError("target_company_size_min must be <= target_company_size_max")


REQUIRED_ON_CREATE = ("name", "target_industries", "target_roles")


class ICPService:
    def __init__(self, repos: RepoRegistry) -> None:
        self.repos = repos

    def create(self, project_id: int, payload: dict) -> int:
        norm = normalize_icp_payload(payload, is_create=True)
        norm["project_id"] = int(project_id)
        for k in REQUIRED_ON_CREATE:
            if k not in norm or norm[k] in (None, "", []):
                raise ValueError(f"{k} is required")
        validate_icp_payload(norm)
        return self.repos.icps.create(norm)

    def update(self, icp_id: int, payload: dict) -> bool:
        norm = normalize_icp_payload(payload, is_create=False)
        norm.pop("project_id", None)
        validate_icp_payload(norm)
        return self.repos.icps.update(icp_id, norm)

    def summary_for_dashboard(self, icp_id: int) -> dict:
        repos = self.repos
        storage = repos.icps.storage
        # drafts join through lead_candidates (no direct icp_id column)
        drafts_total_row = storage.fetchone(
            "SELECT COUNT(*) AS n FROM email_drafts d "
            "JOIN lead_candidates lc ON lc.id = d.lead_candidate_id "
            "WHERE lc.icp_id = ?",
            (icp_id,),
        )
        drafts_pending_row = storage.fetchone(
            "SELECT COUNT(*) AS n FROM email_drafts d "
            "JOIN lead_candidates lc ON lc.id = d.lead_candidate_id "
            "WHERE lc.icp_id = ? AND d.approved = 0",
            (icp_id,),
        )
        # companies/contacts targeted = those linked via lead_candidates for this ICP
        companies_row = storage.fetchone(
            "SELECT COUNT(DISTINCT company_id) AS n FROM lead_candidates WHERE icp_id = ?",
            (icp_id,),
        )
        contacts_row = storage.fetchone(
            "SELECT COUNT(DISTINCT contact_id) AS n FROM lead_candidates "
            "WHERE icp_id = ? AND contact_id IS NOT NULL",
            (icp_id,),
        )
        return {
            "icp_id": icp_id,
            "companies_targeted": int(companies_row["n"] if companies_row else 0),
            "contacts_targeted": int(contacts_row["n"] if contacts_row else 0),
            "leads_total": repos.lead_candidates.count({"icp_id": icp_id}),
            "leads_ready": repos.lead_candidates.count(
                {"icp_id": icp_id, "lead_status": "ready"}
            ),
            "drafts_total": int(drafts_total_row["n"] if drafts_total_row else 0),
            "drafts_pending": int(drafts_pending_row["n"] if drafts_pending_row else 0),
            "signals_total": repos.signals.count({"icp_id": icp_id}),
        }
