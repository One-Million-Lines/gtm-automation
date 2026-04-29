"""Lead export service — File 19.

Builds CRM-ready CSV/JSON bundles for qualified leads, with pluggable
destination adapters (filesystem default; HubSpot + Salesforce stubs).
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Any, Optional, Protocol

from repositories import RepoRegistry
from vtutils.misc import now_iso
from vtutils.vtlogger import getLog

vtlog = getLog("services.export")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWED_DESTINATIONS = ("filesystem", "hubspot", "salesforce")
ALLOWED_FORMATS = ("csv", "json")
ALLOWED_TIERS = ("A", "B", "C", "D")

CSV_COLUMNS = (
    "lead_id",
    "priority_tier",
    "final_score",
    "company_name",
    "company_domain",
    "company_industry",
    "contact_full_name",
    "contact_first_name",
    "contact_last_name",
    "contact_email",
    "contact_job_title",
    "icp_id",
    "icp_name",
    "outreach_message_id",
    "outreach_status",
    "outreach_subject",
    "outreach_body",
    "variant_id",
    "variant_name",
    "is_winning_variant",
)


# ---------------------------------------------------------------------------
# Destination Protocol + adapters
# ---------------------------------------------------------------------------
class Destination(Protocol):
    name: str

    def deliver(self, export: dict, items: list[dict], artifact_path: Optional[str]) -> dict: ...


class FilesystemDestination:
    name = "filesystem"

    def deliver(self, export: dict, items: list[dict], artifact_path: Optional[str]) -> dict:
        # The artifact has already been written to data/exports/{id}/leads.{ext}
        # by run_export(). Filesystem delivery is a no-op confirmation.
        return {
            "destination": "filesystem",
            "delivered": True,
            "artifact_path": artifact_path,
            "row_count": len(items),
            "delivered_at": now_iso(),
        }


class HubSpotDestination:
    name = "hubspot"

    def deliver(self, export: dict, items: list[dict], artifact_path: Optional[str]) -> dict:
        vtlog.info(
            "HubSpot stub: would upsert %d leads from export id=%s",
            len(items),
            export.get("id"),
        )
        return {
            "destination": "hubspot",
            "delivered": True,
            "simulated": True,
            "row_count": len(items),
            "fake_response": {
                "status": 202,
                "batch_id": f"hs_batch_{export.get('id')}",
                "items_accepted": len(items),
            },
            "delivered_at": now_iso(),
        }


class SalesforceDestination:
    name = "salesforce"

    def deliver(self, export: dict, items: list[dict], artifact_path: Optional[str]) -> dict:
        vtlog.info(
            "Salesforce stub: would create %d Lead records from export id=%s",
            len(items),
            export.get("id"),
        )
        return {
            "destination": "salesforce",
            "delivered": True,
            "simulated": True,
            "row_count": len(items),
            "fake_response": {
                "status": "queued",
                "job_id": f"sf_job_{export.get('id')}",
                "items_accepted": len(items),
            },
            "delivered_at": now_iso(),
        }


# ---------------------------------------------------------------------------
# Pluggable destination registry
# ---------------------------------------------------------------------------
def _build_default_destinations() -> dict[str, Destination]:
    return {
        "filesystem": FilesystemDestination(),
        "hubspot": HubSpotDestination(),
        "salesforce": SalesforceDestination(),
    }


_default_destinations: dict[str, Destination] = _build_default_destinations()


def get_default_destinations() -> dict[str, Destination]:
    return _default_destinations


def get_default_destination(name: str) -> Destination:
    if name not in _default_destinations:
        raise ValueError(f"unknown destination: {name}")
    return _default_destinations[name]


def set_default_destination(name: str, destination: Optional[Destination]) -> None:
    """Override (or reset to default with destination=None) a single adapter."""
    global _default_destinations
    if destination is None:
        _default_destinations[name] = _build_default_destinations()[name]
    else:
        _default_destinations[name] = destination


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------
def _winning_variant(repos: RepoRegistry, lead: dict) -> Optional[dict]:
    """Find the winning variant for a lead via lead_variant_assignments + experiment.winner_variant_id."""
    lead_id = int(lead["id"])
    assignments = repos.lead_variant_assignments.find({"lead_id": lead_id})
    for a in assignments:
        exp = repos.outreach_experiments.get(int(a["experiment_id"]))
        if not exp:
            continue
        winner_id = exp.get("winner_variant_id")
        if winner_id and int(winner_id) == int(a["variant_id"]):
            variant = repos.outreach_variants.get(int(winner_id))
            if variant:
                variant = dict(variant)
                variant["experiment_id"] = exp["id"]
                variant["experiment_name"] = exp.get("name")
                return variant
    return None


def _best_outreach_message(repos: RepoRegistry, lead_id: int) -> Optional[dict]:
    """Latest 'sent' outreach message; else latest 'approved'; else latest of any."""
    rows = repos.outreach_messages.find(
        {"lead_id": lead_id},
        order_by="generated_at DESC, id DESC",
        limit=20,
    )
    if not rows:
        return None
    for status in ("sent", "approved"):
        for r in rows:
            if (r.get("status") or "").lower() == status:
                return r
    return rows[0]


def build_payload_for_lead(repos: RepoRegistry, lead: dict) -> dict:
    """Assemble the full CRM payload for a single lead."""
    company = repos.companies.get(int(lead["company_id"])) if lead.get("company_id") else None
    contact = repos.contacts.get(int(lead["contact_id"])) if lead.get("contact_id") else None
    icp = repos.icps.get(int(lead["icp_id"])) if lead.get("icp_id") else None
    msg = _best_outreach_message(repos, int(lead["id"]))
    winning_variant = _winning_variant(repos, lead)

    msg_variant = None
    is_winning = False
    if msg and msg.get("variant_id"):
        msg_variant = repos.outreach_variants.get(int(msg["variant_id"]))
        if winning_variant and msg_variant and int(msg_variant["id"]) == int(winning_variant["id"]):
            is_winning = True

    return {
        "lead": {
            "id": lead["id"],
            "priority_tier": lead.get("priority_tier"),
            "final_score": lead.get("final_score"),
            "lead_status": lead.get("lead_status"),
            "icp_id": lead.get("icp_id"),
            "company_id": lead.get("company_id"),
            "contact_id": lead.get("contact_id"),
        },
        "company": _slim_company(company),
        "contact": _slim_contact(contact),
        "icp": _slim_icp(icp),
        "outreach_message": _slim_message(msg, msg_variant),
        "winning_variant": _slim_variant(winning_variant) if winning_variant else None,
        "is_winning_variant": is_winning,
    }


def _slim_company(c: Optional[dict]) -> Optional[dict]:
    if not c:
        return None
    return {
        "id": c.get("id"),
        "name": c.get("name"),
        "domain": c.get("domain"),
        "industry": c.get("industry"),
        "country": c.get("country"),
        "employee_count": c.get("employee_count"),
    }


def _slim_contact(c: Optional[dict]) -> Optional[dict]:
    if not c:
        return None
    return {
        "id": c.get("id"),
        "first_name": c.get("first_name"),
        "last_name": c.get("last_name"),
        "full_name": c.get("full_name"),
        "email": c.get("email"),
        "job_title": c.get("job_title"),
        "linkedin_url": c.get("linkedin_url"),
    }


def _slim_icp(i: Optional[dict]) -> Optional[dict]:
    if not i:
        return None
    return {"id": i.get("id"), "name": i.get("name")}


def _slim_message(m: Optional[dict], variant: Optional[dict]) -> Optional[dict]:
    if not m:
        return None
    return {
        "id": m.get("id"),
        "status": m.get("status"),
        "subject": m.get("subject"),
        "body": m.get("body"),
        "variant_id": m.get("variant_id"),
        "variant_name": variant.get("name") if variant else None,
        "generated_at": m.get("generated_at"),
        "approved_at": m.get("approved_at"),
        "sent_at": m.get("sent_at"),
    }


def _slim_variant(v: dict) -> dict:
    return {
        "id": v.get("id"),
        "name": v.get("name"),
        "experiment_id": v.get("experiment_id"),
        "experiment_name": v.get("experiment_name"),
        "is_control": v.get("is_control"),
    }


# ---------------------------------------------------------------------------
# Lead selection
# ---------------------------------------------------------------------------
def _filter_leads(
    repos: RepoRegistry,
    *,
    project_id: int,
    icp_id: Optional[int],
    filters: Optional[dict],
) -> list[dict]:
    query: dict = {"project_id": project_id}
    if icp_id is not None:
        query["icp_id"] = icp_id
    rows = repos.lead_candidates.find(query, order_by="final_score DESC, id ASC", limit=5000)

    f = filters or {}
    tiers = f.get("priority_tier") or f.get("tiers")
    if tiers:
        if isinstance(tiers, str):
            tiers = [tiers]
        tier_set = {str(t).upper() for t in tiers}
        rows = [r for r in rows if (r.get("priority_tier") or "").upper() in tier_set]

    min_score = f.get("min_score")
    if min_score is not None:
        try:
            ms = float(min_score)
            rows = [r for r in rows if (r.get("final_score") or 0) >= ms]
        except (TypeError, ValueError):
            pass

    statuses = f.get("lead_status")
    if statuses:
        if isinstance(statuses, str):
            statuses = [statuses]
        s_set = {str(s).lower() for s in statuses}
        rows = [r for r in rows if (r.get("lead_status") or "").lower() in s_set]

    limit = f.get("limit")
    if limit:
        try:
            rows = rows[: int(limit)]
        except (TypeError, ValueError):
            pass

    return rows


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------
def _exports_root() -> Path:
    here = Path(__file__).resolve().parent.parent
    return here / "data" / "exports"


def _flatten_for_csv(payload: dict) -> dict:
    lead = payload.get("lead") or {}
    company = payload.get("company") or {}
    contact = payload.get("contact") or {}
    icp = payload.get("icp") or {}
    msg = payload.get("outreach_message") or {}
    win = payload.get("winning_variant") or {}
    return {
        "lead_id": lead.get("id"),
        "priority_tier": lead.get("priority_tier"),
        "final_score": lead.get("final_score"),
        "company_name": company.get("name"),
        "company_domain": company.get("domain"),
        "company_industry": company.get("industry"),
        "contact_full_name": contact.get("full_name"),
        "contact_first_name": contact.get("first_name"),
        "contact_last_name": contact.get("last_name"),
        "contact_email": contact.get("email"),
        "contact_job_title": contact.get("job_title"),
        "icp_id": icp.get("id"),
        "icp_name": icp.get("name"),
        "outreach_message_id": msg.get("id"),
        "outreach_status": msg.get("status"),
        "outreach_subject": msg.get("subject"),
        "outreach_body": msg.get("body"),
        "variant_id": msg.get("variant_id"),
        "variant_name": msg.get("variant_name") or win.get("name"),
        "is_winning_variant": int(bool(payload.get("is_winning_variant"))),
    }


def _write_csv(path: Path, payloads: list[dict]) -> int:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(CSV_COLUMNS))
    writer.writeheader()
    for p in payloads:
        writer.writerow(_flatten_for_csv(p))
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path.stat().st_size


def _write_json(path: Path, payloads: list[dict]) -> int:
    path.write_text(json.dumps(payloads, indent=2, default=str), encoding="utf-8")
    return path.stat().st_size


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_export(
    repos: RepoRegistry,
    *,
    project_id: int,
    icp_id: Optional[int] = None,
    name: str,
    destination: str = "filesystem",
    format: str = "csv",
    filters: Optional[dict] = None,
    dry_run: bool = False,
    destinations: Optional[dict[str, Destination]] = None,
) -> dict:
    if destination not in ALLOWED_DESTINATIONS:
        raise ValueError(f"invalid destination: {destination}")
    if format not in ALLOWED_FORMATS:
        raise ValueError(f"invalid format: {format}")
    if not name or not str(name).strip():
        raise ValueError("name is required")

    project = repos.projects.get(project_id)
    if not project:
        raise ValueError(f"project not found: {project_id}")

    export_id = repos.lead_exports.create({
        "project_id": project_id,
        "icp_id": icp_id,
        "name": str(name).strip(),
        "destination": destination,
        "format": format,
        "filters": filters or {},
        "status": "pending",
    })

    repos.lead_exports.set_status(export_id, "building", started_at=now_iso())

    leads = _filter_leads(repos, project_id=project_id, icp_id=icp_id, filters=filters)

    payloads: list[dict] = []
    items_to_create: list[dict] = []
    for lead in leads:
        payload = build_payload_for_lead(repos, lead)
        payloads.append(payload)
        msg = payload.get("outreach_message") or {}
        win = payload.get("winning_variant") or {}
        items_to_create.append({
            "lead_export_id": export_id,
            "lead_id": int(lead["id"]),
            "outreach_message_id": msg.get("id"),
            "variant_id": msg.get("variant_id") or win.get("id"),
            "payload": payload,
        })

    repos.lead_export_items.bulk_create(items_to_create)

    artifact_path: Optional[str] = None
    artifact_size: Optional[int] = None

    if dry_run:
        repos.lead_exports.set_artifact(
            export_id,
            artifact_path=None,
            artifact_size_bytes=None,
            row_count=len(payloads),
            status="ready",
        )
        export = repos.lead_exports.get(export_id)
        return {
            "export": export,
            "row_count": len(payloads),
            "delivery": {"destination": destination, "delivered": False, "dry_run": True},
        }

    try:
        export_dir = _exports_root() / str(export_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        out_path = export_dir / f"leads.{format}"
        if format == "csv":
            artifact_size = _write_csv(out_path, payloads)
        else:
            artifact_size = _write_json(out_path, payloads)
        artifact_path = str(out_path)
    except Exception as exc:  # pragma: no cover - filesystem failure
        repos.lead_exports.set_status(
            export_id, "failed", error_message=f"artifact write failed: {exc}",
        )
        raise

    repos.lead_exports.set_artifact(
        export_id,
        artifact_path=artifact_path,
        artifact_size_bytes=artifact_size,
        row_count=len(payloads),
        status="ready",
    )

    adapters = destinations or get_default_destinations()
    adapter = adapters.get(destination) or get_default_destination(destination)
    delivery: dict
    items_for_adapter = repos.lead_export_items.list_for_export(export_id)
    try:
        delivery = adapter.deliver(repos.lead_exports.get(export_id), items_for_adapter, artifact_path)
        repos.lead_exports.set_delivered(export_id, status="delivered")
    except Exception as exc:
        delivery = {"destination": destination, "delivered": False, "error": str(exc)}
        repos.lead_exports.set_delivered(export_id, status="failed", error_message=str(exc))

    export = repos.lead_exports.get(export_id)
    return {
        "export": export,
        "row_count": len(payloads),
        "artifact_path": artifact_path,
        "artifact_size_bytes": artifact_size,
        "delivery": delivery,
    }


def redeliver(
    repos: RepoRegistry,
    export_id: int,
    *,
    destinations: Optional[dict[str, Destination]] = None,
) -> dict:
    export = repos.lead_exports.get(export_id)
    if not export:
        raise ValueError(f"export not found: {export_id}")

    adapters = destinations or get_default_destinations()
    adapter = adapters.get(export["destination"]) or get_default_destination(export["destination"])
    items = repos.lead_export_items.list_for_export(export_id)
    try:
        delivery = adapter.deliver(export, items, export.get("artifact_path"))
        repos.lead_exports.set_delivered(export_id, status="delivered")
    except Exception as exc:
        delivery = {"destination": export["destination"], "delivered": False, "error": str(exc)}
        repos.lead_exports.set_delivered(export_id, status="failed", error_message=str(exc))
    return {"export": repos.lead_exports.get(export_id), "delivery": delivery}


def delivery_summary(repos: RepoRegistry, export_id: int) -> dict:
    export = repos.lead_exports.get(export_id)
    if not export:
        raise ValueError(f"export not found: {export_id}")
    return {
        "row_count": export.get("row_count") or 0,
        "artifact_size_bytes": export.get("artifact_size_bytes"),
        "destination": export.get("destination"),
        "status": export.get("status"),
        "artifact_path": export.get("artifact_path"),
        "error_message": export.get("error_message"),
    }
