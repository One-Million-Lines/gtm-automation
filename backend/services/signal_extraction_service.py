"""Signal extraction service — orchestrates DetectedSignal -> signals rows.

Pure-ish: takes a `repos`, optional `provider`, optional filters. Persists
signals (and a `signal_evidence` row when source_url is present), returns a
JSON-friendly summary.
"""
from __future__ import annotations

import hashlib
from typing import Any

from services.signal_provider import (
    DetectedSignal, SIGNAL_TYPES, SignalProvider, get_default_signal_provider,
)


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

def _select_company_ids(
    repos, *,
    project_id: int | None,
    company_id: int | None,
    company_ids: list[int] | None,
    limit: int,
) -> list[int]:
    if company_ids:
        return [int(x) for x in company_ids]
    if company_id is not None:
        return [int(company_id)]
    if project_id is not None:
        # companies have no project_id; JOIN through lead_candidates
        sql = (
            "SELECT DISTINCT c.id AS id FROM companies c "
            "JOIN lead_candidates lc ON lc.company_id = c.id "
            "WHERE lc.project_id = ? ORDER BY c.id ASC LIMIT ?"
        )
        rows = repos.companies.storage.fetchall(sql, (int(project_id), int(limit)))
        return [int(r["id"]) for r in rows]
    return []


def _select_contact_ids(
    repos, *,
    project_id: int | None,
    company_id: int | None,
    contact_ids: list[int] | None,
    limit: int,
) -> list[int]:
    if contact_ids:
        return [int(x) for x in contact_ids]
    if company_id is not None:
        rows = repos.contacts.find(
            {"company_id": int(company_id)}, order_by="id ASC", limit=limit,
        )
        return [int(r["id"]) for r in rows]
    if project_id is not None:
        # contacts have no project_id; JOIN through lead_candidates
        sql = (
            "SELECT DISTINCT c.id AS id FROM contacts c "
            "JOIN lead_candidates lc ON lc.contact_id = c.id "
            "WHERE lc.project_id = ? ORDER BY c.id ASC LIMIT ?"
        )
        rows = repos.contacts.storage.fetchall(sql, (int(project_id), int(limit)))
        return [int(r["id"]) for r in rows]
    return []


def _latest_two_enrichments(repos, company_id: int) -> tuple[dict | None, dict | None]:
    rows = repos.company_enrichment.find(
        {"company_id": int(company_id)},
        order_by="created_at DESC, id DESC",
        limit=2,
    )
    latest = rows[0] if rows else None
    previous = rows[1] if len(rows) > 1 else None
    return latest, previous


def _fingerprint(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("company_id") or ""),
        str(row.get("contact_id") or ""),
        row.get("signal_type") or "",
        row.get("signal_name") or "",
        row.get("source_url") or "",
    ]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _persist(repos, row: dict[str, Any]) -> int:
    sid = repos.signals.create(row)
    if row.get("source_url"):
        try:
            repos.signal_evidence.create({
                "signal_id": int(sid),
                "evidence_type": row.get("signal_type") or "homepage",
                "source_url": row.get("source_url"),
                "extracted_text": row.get("extracted_text"),
                "snippet": (row.get("description") or "")[:500],
                "confidence_score": row.get("confidence_score"),
                "raw_data": row.get("raw_data") or {},
                "fingerprint": _fingerprint(row),
            })
        except Exception:
            pass
    return int(sid)


def _filter_signal_types(
    signals: list[DetectedSignal],
    signal_types: list[str] | None,
) -> list[DetectedSignal]:
    if not signal_types:
        return signals
    keep = {s for s in signal_types if s in SIGNAL_TYPES}
    return [s for s in signals if s.signal_type in keep]


# ---------------------------------------------------------------------------
# Single-entity extractors
# ---------------------------------------------------------------------------

def extract_company_signals_for(
    repos,
    company_id: int,
    *,
    icp_id: int | None = None,
    provider: SignalProvider | None = None,
    signal_types: list[str] | None = None,
    only_missing: bool = False,
    dry_run: bool = False,
    detected_by: str = "live",
) -> dict[str, Any]:
    company = repos.companies.get(int(company_id))
    if not company:
        return {"company_id": company_id, "ok": False, "skipped": True,
                "error": "company_not_found", "signals": [], "persisted": 0}

    if only_missing and repos.signals.count({"company_id": int(company_id)}) > 0:
        return {"company_id": company_id, "ok": True, "skipped": True,
                "error": "already_has_signals", "signals": [], "persisted": 0}

    latest, previous = _latest_two_enrichments(repos, int(company_id))

    p = provider or get_default_signal_provider()
    detected = p.extract_company(
        company=company, latest_enrichment=latest, previous_enrichment=previous,
    )
    detected = _filter_signal_types(detected, signal_types)

    persisted: list[int] = []
    rows: list[dict[str, Any]] = []
    for s in detected:
        row = s.to_row(company_id=int(company_id), contact_id=None,
                       icp_id=int(icp_id) if icp_id else None,
                       detected_by=detected_by)
        if not dry_run:
            sid = _persist(repos, row)
            row["id"] = sid
            persisted.append(sid)
        rows.append(row)

    return {
        "company_id": int(company_id),
        "ok": True,
        "skipped": False,
        "detected": len(detected),
        "persisted": len(persisted),
        "signals": rows,
        "dry_run": dry_run,
    }


def extract_contact_signals_for(
    repos,
    contact_id: int,
    *,
    icp_id: int | None = None,
    provider: SignalProvider | None = None,
    signal_types: list[str] | None = None,
    only_missing: bool = False,
    dry_run: bool = False,
    detected_by: str = "live",
) -> dict[str, Any]:
    contact = repos.contacts.get(int(contact_id))
    if not contact:
        return {"contact_id": contact_id, "ok": False, "skipped": True,
                "error": "contact_not_found", "signals": [], "persisted": 0}

    if only_missing and repos.signals.count({"contact_id": int(contact_id)}) > 0:
        return {"contact_id": contact_id, "ok": True, "skipped": True,
                "error": "already_has_signals", "signals": [], "persisted": 0}

    p = provider or get_default_signal_provider()
    detected = p.extract_contact(contact=contact, previous_contact=None)
    detected = _filter_signal_types(detected, signal_types)

    persisted: list[int] = []
    rows: list[dict[str, Any]] = []
    for s in detected:
        row = s.to_row(company_id=contact.get("company_id"), contact_id=int(contact_id),
                       icp_id=int(icp_id) if icp_id else None,
                       detected_by=detected_by)
        if not dry_run:
            sid = _persist(repos, row)
            row["id"] = sid
            persisted.append(sid)
        rows.append(row)

    return {
        "contact_id": int(contact_id),
        "ok": True,
        "skipped": False,
        "detected": len(detected),
        "persisted": len(persisted),
        "signals": rows,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def run_signals_batch(
    repos,
    *,
    project_id: int | None = None,
    company_id: int | None = None,
    company_ids: list[int] | None = None,
    contact_ids: list[int] | None = None,
    signal_types: list[str] | None = None,
    icp_id: int | None = None,
    limit: int = 100,
    only_missing: bool = True,
    dry_run: bool = False,
    provider: SignalProvider | None = None,
    detected_by: str = "api",
) -> dict[str, Any]:
    p = provider or get_default_signal_provider()

    co_ids = _select_company_ids(
        repos, project_id=project_id, company_id=company_id,
        company_ids=company_ids, limit=limit,
    )
    # If contact_ids explicitly provided, run only contacts. Otherwise also pull
    # contacts that belong to selected companies (or project).
    if contact_ids:
        ct_ids = [int(x) for x in contact_ids]
    else:
        ct_ids = _select_contact_ids(
            repos, project_id=project_id, company_id=company_id,
            contact_ids=None, limit=limit,
        )

    company_results: list[dict[str, Any]] = []
    contact_results: list[dict[str, Any]] = []
    total_persisted = 0
    failed = 0

    for cid in co_ids:
        try:
            r = extract_company_signals_for(
                repos, cid, icp_id=icp_id, provider=p,
                signal_types=signal_types, only_missing=only_missing,
                dry_run=dry_run, detected_by=detected_by,
            )
            company_results.append(r)
            total_persisted += r.get("persisted", 0)
        except Exception as e:  # noqa: BLE001
            failed += 1
            company_results.append({"company_id": cid, "ok": False, "error": str(e)})

    for cid in ct_ids:
        try:
            r = extract_contact_signals_for(
                repos, cid, icp_id=icp_id, provider=p,
                signal_types=signal_types, only_missing=only_missing,
                dry_run=dry_run, detected_by=detected_by,
            )
            contact_results.append(r)
            total_persisted += r.get("persisted", 0)
        except Exception as e:  # noqa: BLE001
            failed += 1
            contact_results.append({"contact_id": cid, "ok": False, "error": str(e)})

    return {
        "scanned_companies": len(co_ids),
        "scanned_contacts": len(ct_ids),
        "persisted": total_persisted,
        "failed": failed,
        "dry_run": dry_run,
        "company_results": company_results,
        "contact_results": contact_results,
    }
