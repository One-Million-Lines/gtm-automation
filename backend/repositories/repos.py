"""All entity repositories. Most are 2 lines: declare table + json_fields."""
from __future__ import annotations

from typing import Any, Iterable

from repositories.base_repo import BaseRepo
from vtutils.misc import now_iso


# ============================================================================
# Simple repos (table + json_fields only)
# ============================================================================
class ProjectRepo(BaseRepo):
    table = "projects"


class ICPRepo(BaseRepo):
    table = "icps"
    json_fields = (
        "target_industries", "target_geographies", "target_company_sizes",
        "target_personas", "target_roles", "target_seniorities",
        "pain_points", "competitors",
        "buying_signals", "exclusion_rules",
    )

    def find_for_project(self, project_id: int, status: str | None = None) -> list[dict]:
        where: dict = {"project_id": project_id}
        if status:
            where["status"] = status
        return self.find(where, order_by="id DESC")

    def find_active_for_project(self, project_id: int) -> list[dict]:
        return self.find_for_project(project_id, status="active")

    def activate(self, icp_id: int) -> bool:
        return self.update(icp_id, {"status": "active"})

    def archive(self, icp_id: int) -> bool:
        return self.update(icp_id, {"status": "archived"})

    def clone(self, icp_id: int, new_name: str) -> int:
        src = self.get(icp_id)
        if not src:
            raise ValueError(f"ICP {icp_id} not found")
        copy = {k: v for k, v in src.items() if k not in ("id", "created_at", "updated_at")}
        copy["name"] = new_name
        copy["status"] = "draft"
        return self.create(copy)


class CompanySourceRepo(BaseRepo):
    table = "company_sources"
    json_fields = ("raw_data",)
    has_updated_at = False


class CompanyEnrichmentRepo(BaseRepo):
    table = "company_enrichment"
    json_fields = ("tech_stack", "social_links", "raw_data")
    has_updated_at = False


class ContactSourceRepo(BaseRepo):
    table = "contact_sources"
    json_fields = ("raw_data",)
    has_updated_at = False


class ContactEnrichmentRepo(BaseRepo):
    table = "contact_enrichment"
    json_fields = ("raw_data",)
    has_updated_at = False


class SignalEvidenceRepo(BaseRepo):
    table = "signal_evidence"
    json_fields = ("raw_data",)
    has_updated_at = False


class DraftQualityCheckRepo(BaseRepo):
    table = "draft_quality_checks"
    json_fields = ("details",)
    has_updated_at = False


class CampaignRepo(BaseRepo):
    table = "campaigns"


class CampaignEventRepo(BaseRepo):
    table = "campaign_events"
    json_fields = ("raw_data",)
    has_updated_at = False


# ============================================================================
# Repos with entity-specific methods
# ============================================================================
class CompanyRepo(BaseRepo):
    table = "companies"
    json_fields = ("tech_stack",)

    def upsert_by_domain(self, data: dict) -> int:
        """Insert or update on domain conflict. Returns the company id."""
        if not data.get("domain"):
            raise ValueError("upsert_by_domain requires 'domain'")
        self.upsert_one(data, conflict_cols=("domain",))
        row = self.storage.get_one("companies", {"domain": data["domain"]}, columns="id")
        return int(row["id"]) if row else 0

    def find_by_status(self, status: str, limit: int = 100) -> list[dict]:
        return self.find({"status": status}, order_by="created_at ASC", limit=limit)


class ContactRepo(BaseRepo):
    table = "contacts"

    def upsert_by_email(self, data: dict) -> int:
        """Email is not a SQL UNIQUE column (multiple NULLs allowed),
        so we emulate upsert in code."""
        email = data.get("email")
        if not email:
            return self.create(data)
        existing = self.find_one({"email": email})
        if existing:
            self.update(int(existing["id"]), data)
            return int(existing["id"])
        return self.create(data)

    def find_by_company(self, company_id: int) -> list[dict]:
        return self.find({"company_id": company_id}, order_by="created_at ASC")

    def get_by_email(self, email: str | None) -> dict | None:
        if not email:
            return None
        return self.find_one({"email": email.strip().lower()})

    def get_by_linkedin(self, linkedin_url: str | None) -> dict | None:
        if not linkedin_url:
            return None
        return self.find_one({"linkedin_url": linkedin_url})

    def get_by_company_and_name(self, company_id: int, full_name_lower: str | None) -> dict | None:
        if not full_name_lower:
            return None
        rows = self.storage.fetchall(
            "SELECT * FROM contacts WHERE company_id = ? AND LOWER(full_name) = ? LIMIT 1",
            (company_id, full_name_lower),
        )
        return self._decode(rows[0]) if rows else None

    def upsert_contact(self, payload: dict) -> tuple[int, str]:
        """Dedupe order: email -> linkedin_url -> (company_id, full_name lower).
        Returns (contact_id, action) where action is 'created'|'updated'.
        """
        existing: dict | None = None
        email = (payload.get("email") or "").strip().lower() or None
        if email:
            existing = self.get_by_email(email)
        if not existing and payload.get("linkedin_url"):
            existing = self.get_by_linkedin(payload["linkedin_url"])
        if not existing and payload.get("company_id") and payload.get("full_name"):
            existing = self.get_by_company_and_name(
                int(payload["company_id"]),
                str(payload["full_name"]).strip().lower(),
            )
        if existing:
            self.update(int(existing["id"]), payload)
            return int(existing["id"]), "updated"
        return self.create(payload), "created"


class LeadResearchRepo(BaseRepo):
    table = "lead_research"
    json_fields = ("talking_points", "evidence")

    def latest_for_lead(self, lead_candidate_id: int) -> dict | None:
        rows = self.find(
            {"lead_candidate_id": lead_candidate_id},
            order_by="created_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None


class SignalRepo(BaseRepo):
    table = "signals"
    json_fields = ("raw_data",)
    has_updated_at = False

    def find_by_company(self, company_id: int, limit: int = 200) -> list[dict]:
        return self.find({"company_id": company_id}, order_by="created_at DESC", limit=limit)

    def find_by_company_type(self, company_id: int, signal_type: str) -> list[dict]:
        return self.find(
            {"company_id": company_id, "signal_type": signal_type},
            order_by="created_at DESC",
        )


class LeadCandidateRepo(BaseRepo):
    table = "lead_candidates"
    json_fields = ("scoring_explanation",)

    def upsert(
        self,
        icp_id: int,
        company_id: int,
        contact_id: int | None,
        data: dict,
    ) -> int:
        """Per schema spec: avoid duplicates on (icp_id, company_id, contact_id).
        SQLite treats NULLs as distinct, so handle contact_id IS NULL in code."""
        query = {"icp_id": icp_id, "company_id": company_id, "contact_id": contact_id}
        existing = self.find_one(query)
        payload = dict(data)
        payload.update({"icp_id": icp_id, "company_id": company_id, "contact_id": contact_id})
        if existing:
            self.update(int(existing["id"]), payload)
            return int(existing["id"])
        return self.create(payload)

    def upsert_full(
        self,
        icp_id: int,
        company_id: int,
        contact_id: int,
        data: dict,
    ) -> tuple[int, str]:
        """Strategy: a contact-discovery upsert for a (icp_id, company_id, contact_id).

        1) If a row exists for (icp_id, company_id, contact_id) -> update it.
        2) Else if a placeholder row exists for (icp_id, company_id, NULL contact)
           -> attach this contact to that row (avoids duplicating the lead created
           by File 06 company-discovery).
        3) Else create a new row.
        Returns (lead_id, action) where action is 'created' | 'updated' | 'attached'.
        """
        payload = dict(data)
        payload.update({
            "icp_id": int(icp_id),
            "company_id": int(company_id),
            "contact_id": int(contact_id),
        })
        # 1) exact match
        exact = self.find_one({
            "icp_id": icp_id, "company_id": company_id, "contact_id": contact_id,
        })
        if exact:
            self.update(int(exact["id"]), payload)
            return int(exact["id"]), "updated"
        # 2) placeholder match
        placeholder = self.find_one({
            "icp_id": icp_id, "company_id": company_id, "contact_id": None,
        })
        if placeholder:
            self.update(int(placeholder["id"]), payload)
            return int(placeholder["id"]), "attached"
        # 3) create new
        return self.create(payload), "created"

    def list_ready(self, project_id: int, limit: int = 500) -> list[dict]:
        return self.find(
            {"project_id": project_id, "ready_for_outreach": 1},
            order_by="final_score DESC",
            limit=limit,
        )

    def find_by_status(self, project_id: int, status: str, limit: int = 500) -> list[dict]:
        return self.find(
            {"project_id": project_id, "lead_status": status},
            order_by="updated_at DESC",
            limit=limit,
        )

    def set_status(self, lead_id: int, status: str, **extra: Any) -> int:
        return self.update(lead_id, {"lead_status": status, **extra})


class EmailDraftRepo(BaseRepo):
    table = "email_drafts"
    json_fields = ("source_evidence",)

    def latest_for_lead(self, lead_candidate_id: int) -> dict | None:
        rows = self.find(
            {"lead_candidate_id": lead_candidate_id},
            order_by="created_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None

    def find_approved_for_lead(self, lead_candidate_id: int) -> dict | None:
        rows = self.find(
            {"lead_candidate_id": lead_candidate_id, "approved": 1},
            order_by="created_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None


class OutreachMessageRepo(BaseRepo):
    table = "outreach_messages"
    json_fields = ("context", "raw_response")

    def latest_for_lead(self, lead_id: int) -> dict | None:
        rows = self.find(
            {"lead_id": lead_id},
            order_by="generated_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None

    def history_for_lead(self, lead_id: int, limit: int = 50) -> list[dict]:
        return self.find(
            {"lead_id": lead_id},
            order_by="generated_at DESC, id DESC",
            limit=limit,
        )


class QualityCheckRepo(BaseRepo):
    table = "quality_checks"
    json_fields = ("rule_results",)
    has_updated_at = False

    def latest_for_message(self, outreach_message_id: int) -> dict | None:
        rows = self.find(
            {"outreach_message_id": outreach_message_id},
            order_by="created_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None

    def history_for_message(self, outreach_message_id: int, limit: int = 50) -> list[dict]:
        return self.find(
            {"outreach_message_id": outreach_message_id},
            order_by="created_at DESC, id DESC",
            limit=limit,
        )


class OutreachSendRepo(BaseRepo):
    table = "outreach_sends"
    json_fields = ("raw_response",)
    has_updated_at = False

    def latest_for_message(self, outreach_message_id: int) -> dict | None:
        rows = self.find(
            {"outreach_message_id": outreach_message_id},
            order_by="attempted_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None

    def history_for_message(self, outreach_message_id: int, limit: int = 50) -> list[dict]:
        return self.find(
            {"outreach_message_id": outreach_message_id},
            order_by="attempted_at DESC, id DESC",
            limit=limit,
        )

    def count_sent_today(self, project_id: int) -> int:
        sql = (
            "SELECT COUNT(*) AS n FROM outreach_sends os "
            "INNER JOIN outreach_messages om ON om.id = os.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            "WHERE lc.project_id = ? AND os.status = 'sent' "
            "AND date(COALESCE(os.sent_at, os.attempted_at)) = date('now')"
        )
        rows = self.storage.fetchall(sql, (int(project_id),))
        return int(rows[0]["n"]) if rows else 0


class OutreachReplyRepo(BaseRepo):
    table = "outreach_replies"
    json_fields = ("raw_response",)
    has_updated_at = False

    def latest_for_message(self, outreach_message_id: int) -> dict | None:
        rows = self.find(
            {"outreach_message_id": outreach_message_id},
            order_by="received_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None

    def history_for_message(self, outreach_message_id: int, limit: int = 50) -> list[dict]:
        return self.find(
            {"outreach_message_id": outreach_message_id},
            order_by="received_at DESC, id DESC",
            limit=limit,
        )

    def list_for_project(
        self, project_id: int, *,
        intent: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where = ["lc.project_id = ?"]
        params: list[Any] = [int(project_id)]
        if intent:
            where.append("orep.intent = ?")
            params.append(intent)
        sql = (
            "SELECT orep.* FROM outreach_replies orep "
            "INNER JOIN outreach_messages om ON om.id = orep.outreach_message_id "
            "INNER JOIN lead_candidates lc ON lc.id = om.lead_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY orep.received_at DESC, orep.id DESC LIMIT ?"
        )
        params.append(int(limit))
        return self._decode_many(self.storage.fetchall(sql, tuple(params)))


class EngagementSnapshotRepo(BaseRepo):
    table = "engagement_snapshots"
    json_fields = ("payload",)
    has_updated_at = False

    def latest_for(self, project_id: int, *, icp_id: int | None = None,
                   window_days: int = 30) -> dict | None:
        where = ["project_id = ?", "window_days = ?"]
        params: list[Any] = [int(project_id), int(window_days)]
        if icp_id is None:
            where.append("icp_id IS NULL")
        else:
            where.append("icp_id = ?")
            params.append(int(icp_id))
        sql = (
            f"SELECT * FROM {self.table} WHERE {' AND '.join(where)} "
            "ORDER BY computed_at DESC, id DESC LIMIT 1"
        )
        rows = self.storage.fetchall(sql, tuple(params))
        return self._decode(rows[0]) if rows else None

    def upsert_for(self, project_id: int, icp_id: int | None,
                   window_days: int, payload: dict) -> int:
        existing = self.latest_for(project_id, icp_id=icp_id, window_days=window_days)
        data = {
            "project_id": int(project_id),
            "icp_id": int(icp_id) if icp_id is not None else None,
            "window_days": int(window_days),
            "computed_at": now_iso(),
            "payload": payload,
        }
        if existing:
            self.update(int(existing["id"]), data)
            return int(existing["id"])
        return self.create(data)


class OutreachExperimentRepo(BaseRepo):
    table = "outreach_experiments"
    json_fields = ("config",)

    def list_for_project(self, project_id: int, *, status: str | None = None,
                         limit: int = 200) -> list[dict]:
        where: dict[str, Any] = {"project_id": int(project_id)}
        if status:
            where["status"] = status
        return self.find(where, order_by="created_at DESC, id DESC", limit=limit)

    def set_status(self, experiment_id: int, status: str, **extra: Any) -> int:
        return self.update(int(experiment_id), {"status": status, **extra})

    def set_winner(self, experiment_id: int, variant_id: int) -> int:
        return self.update(int(experiment_id), {
            "winner_variant_id": int(variant_id),
            "status": "completed",
            "completed_at": now_iso(),
        })


class OutreachVariantRepo(BaseRepo):
    table = "outreach_variants"
    json_fields = ("params",)
    has_updated_at = False

    def list_for_experiment(self, experiment_id: int) -> list[dict]:
        return self.find(
            {"experiment_id": int(experiment_id)},
            order_by="is_control DESC, id ASC",
        )

    def get_control(self, experiment_id: int) -> dict | None:
        rows = self.find(
            {"experiment_id": int(experiment_id), "is_control": 1},
            order_by="id ASC", limit=1,
        )
        return rows[0] if rows else None


class LeadVariantAssignmentRepo(BaseRepo):
    table = "lead_variant_assignments"
    has_updated_at = False

    def get_for_lead(self, lead_id: int, experiment_id: int) -> dict | None:
        return self.find_one({
            "lead_id": int(lead_id), "experiment_id": int(experiment_id),
        })

    def assign_lead(self, lead_id: int, experiment_id: int, variant_id: int) -> tuple[int, str]:
        existing = self.get_for_lead(lead_id, experiment_id)
        if existing:
            return int(existing["id"]), "existing"
        new_id = self.create({
            "lead_id": int(lead_id),
            "experiment_id": int(experiment_id),
            "variant_id": int(variant_id),
            "assigned_at": now_iso(),
        })
        return int(new_id), "created"


class KnowledgeRepo(BaseRepo):
    table = "knowledge_items"
    json_fields = ("tags",)

    def search(
        self,
        project_id: int,
        *,
        icp_id: int | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if icp_id is not None:
            clauses.append("icp_id = ?")
            params.append(icp_id)
        if tags:
            for t in tags:
                clauses.append("tags LIKE ?")
                params.append(f'%"{t}"%')
        sql = (
            f"SELECT * FROM knowledge_items WHERE {' AND '.join(clauses)} "
            f"ORDER BY importance_score DESC NULLS LAST, created_at DESC LIMIT {int(limit)}"
        )
        return self._decode_many(self.storage.fetchall(sql, params))


class SuppressionRepo(BaseRepo):
    table = "suppression_list"
    has_updated_at = False

    def is_suppressed(self, suppression_type: str, value: str) -> bool:
        if not value:
            return False
        return self.exists({"suppression_type": suppression_type, "value": value})

    def add(self, suppression_type: str, value: str, *, reason: str | None = None, source: str | None = None) -> tuple[int, str]:
        """Idempotent add. Returns (id, action) where action is 'created'|'existing'."""
        existing = self.find_one({"suppression_type": suppression_type, "value": value})
        if existing:
            return int(existing["id"]), "existing"
        self.upsert_one(
            {"suppression_type": suppression_type, "value": value, "reason": reason, "source": source},
            conflict_cols=("suppression_type", "value"),
        )
        row = self.find_one({"suppression_type": suppression_type, "value": value})
        return (int(row["id"]) if row else 0), "created"

    def bulk_add(self, rows: Iterable[dict]) -> dict:
        created = 0
        existing = 0
        skipped = 0
        for r in rows:
            stype = r.get("suppression_type")
            value = r.get("value")
            if not stype or not value:
                skipped += 1
                continue
            _, action = self.add(stype, value, reason=r.get("reason"), source=r.get("source"))
            if action == "created":
                created += 1
            else:
                existing += 1
        return {"created": created, "existing": existing, "skipped": skipped}

    def list_filtered(
        self,
        suppression_type: str | None = None,
        q: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM suppression_list WHERE 1=1"
        params: list[Any] = []
        if suppression_type:
            sql += " AND suppression_type = ?"
            params.append(suppression_type)
        if q:
            sql += " AND value LIKE ?"
            params.append(f"%{q.strip().lower()}%")
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        return self._decode_many(self.storage.fetchall(sql, tuple(params)))

    def values_by_type(self) -> dict[str, set[str]]:
        """Load all suppression entries grouped by type for in-memory matching."""
        rows = self.storage.fetchall(
            "SELECT suppression_type, value FROM suppression_list", ()
        )
        out: dict[str, set[str]] = {}
        for r in rows:
            t = r["suppression_type"]
            out.setdefault(t, set()).add(r["value"])
        return out

    def stats_by_type(self) -> dict[str, int]:
        rows = self.storage.fetchall(
            "SELECT suppression_type, COUNT(*) AS n FROM suppression_list GROUP BY suppression_type",
            (),
        )
        return {r["suppression_type"]: int(r["n"]) for r in rows}


class PipelineRunRepo(BaseRepo):
    table = "pipeline_runs"
    json_fields = ("config", "summary")
    has_updated_at = False

    def start(
        self,
        project_id: int,
        icp_id: int | None,
        run_type: str,
        config: dict | None = None,
    ) -> int:
        return self.create({
            "project_id": project_id,
            "icp_id": icp_id,
            "run_type": run_type,
            "status": "running",
            "started_at": now_iso(),
            "config": config or {},
        })

    def finish(
        self,
        run_id: int,
        status: str,
        *,
        total_processed: int = 0,
        total_created: int = 0,
        total_failed: int = 0,
        error_message: str | None = None,
    ) -> int:
        return self.update(run_id, {
            "status": status,
            "finished_at": now_iso(),
            "total_processed": total_processed,
            "total_created": total_created,
            "total_failed": total_failed,
            "error_message": error_message,
        })

    def set_summary(self, run_id: int, summary: dict) -> int:
        return self.update(run_id, {"summary": summary or {}})


class PipelineRunStepRepo(BaseRepo):
    table = "pipeline_run_steps"
    json_fields = ("result_data",)
    has_updated_at = False

    def start(self, pipeline_run_id: int, module_name: str) -> int:
        return self.create({
            "pipeline_run_id": pipeline_run_id,
            "module_name": module_name,
            "status": "running",
            "started_at": now_iso(),
        })

    def finish(
        self,
        step_id: int,
        *,
        status: str = "completed",
        input_count: int = 0,
        output_count: int = 0,
        failed_count: int = 0,
        error_message: str | None = None,
        result_data: dict | None = None,
    ) -> int:
        return self.update(step_id, {
            "status": status,
            "finished_at": now_iso(),
            "input_count": input_count,
            "output_count": output_count,
            "failed_count": failed_count,
            "error_message": error_message,
            "result_data": result_data or {},
        })


class ModuleLogRepo(BaseRepo):
    table = "module_logs"
    json_fields = ("context",)
    has_updated_at = False

    def log(
        self,
        *,
        pipeline_run_id: int | None = None,
        pipeline_run_step_id: int | None = None,
        module_name: str | None = None,
        level: str = "info",
        message: str = "",
        context: dict | None = None,
    ) -> int:
        return self.create({
            "pipeline_run_id": pipeline_run_id,
            "pipeline_run_step_id": pipeline_run_step_id,
            "module_name": module_name,
            "level": level,
            "message": message,
            "context": context or {},
        })


class ExportRepo:
    """Combined repo for export_batches + export_rows."""
    def __init__(self, storage):
        self.storage = storage
        self.batches = BaseRepo.__new__(BaseRepo)
        self.batches.__init__(storage)
        # Configure dynamically (avoid more boilerplate classes)
        self.batches.table = "export_batches"
        self.batches.json_fields = ("filters",)
        self.batches.has_updated_at = False

        self.rows = BaseRepo.__new__(BaseRepo)
        self.rows.__init__(storage)
        self.rows.table = "export_rows"
        self.rows.json_fields = ("payload",)
        self.rows.has_updated_at = False

    def create_batch(self, data: dict) -> int:
        return self.batches.create(data)

    def add_row(self, batch_id: int, lead_candidate_id: int, *, email: str | None = None,
                email_draft_id: int | None = None, payload: dict | None = None) -> int:
        return self.rows.create({
            "export_batch_id": batch_id,
            "lead_candidate_id": lead_candidate_id,
            "email_draft_id": email_draft_id,
            "email": email,
            "payload": payload or {},
        })

    def has_been_exported(self, lead_candidate_id: int) -> bool:
        return self.rows.exists({"lead_candidate_id": lead_candidate_id})

    def finish_batch(self, batch_id: int, *, status: str = "completed",
                     row_count: int = 0, file_path: str | None = None,
                     error_message: str | None = None) -> int:
        return self.batches.update(batch_id, {
            "status": status,
            "row_count": row_count,
            "file_path": file_path,
            "error_message": error_message,
            "completed_at": now_iso(),
        })


class LeadExportRepo(BaseRepo):
    table = "lead_exports"
    json_fields = ("filters",)

    def list_for_project(
        self,
        project_id: int,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        query: dict = {"project_id": project_id}
        if status:
            query["status"] = status
        return self.find(query, order_by="created_at DESC, id DESC", limit=limit)

    def set_status(self, export_id: int, status: str, **extra) -> int:
        payload: dict = {"status": status}
        payload.update(extra)
        return self.update(export_id, payload)

    def set_artifact(
        self,
        export_id: int,
        *,
        artifact_path: str | None,
        artifact_size_bytes: int | None,
        row_count: int,
        status: str = "ready",
    ) -> int:
        return self.update(export_id, {
            "artifact_path": artifact_path,
            "artifact_size_bytes": artifact_size_bytes,
            "row_count": row_count,
            "status": status,
            "completed_at": now_iso(),
        })

    def set_delivered(self, export_id: int, *, status: str = "delivered",
                      error_message: str | None = None) -> int:
        payload: dict = {
            "status": status,
            "delivered_at": now_iso(),
        }
        if error_message is not None:
            payload["error_message"] = error_message
        return self.update(export_id, payload)


class LeadExportItemRepo(BaseRepo):
    table = "lead_export_items"
    json_fields = ("payload",)
    has_updated_at = False

    def list_for_export(self, export_id: int, *, limit: int = 500) -> list[dict]:
        return self.find(
            {"lead_export_id": export_id},
            order_by="id ASC",
            limit=limit,
        )

    def count_for_export(self, export_id: int) -> int:
        return self.count({"lead_export_id": export_id})

    def bulk_create(self, items: list[dict]) -> int:
        if not items:
            return 0
        return self.create_many(items)


class FeedbackEventRepo(BaseRepo):
    table = "feedback_events"
    json_fields = ("payload",)

    def list_for_project(
        self,
        project_id: int,
        *,
        kind: str | None = None,
        source: str | None = None,
        applied: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        query: dict = {"project_id": project_id}
        if kind:
            query["kind"] = kind
        if source:
            query["source"] = source
        if applied is not None:
            query["applied"] = int(applied)
        return self.find(query, order_by="created_at DESC, id DESC", limit=limit)

    def list_unapplied(self, project_id: int, *, limit: int = 200) -> list[dict]:
        return self.find(
            {"project_id": project_id, "applied": 0},
            order_by="created_at ASC, id ASC",
            limit=limit,
        )

    def mark_applied(self, event_id: int) -> int:
        return self.update(event_id, {"applied": 1})

    def count_by_kind(self, project_id: int) -> dict[str, int]:
        sql = (
            "SELECT kind, COUNT(*) AS n FROM feedback_events "
            "WHERE project_id = ? GROUP BY kind"
        )
        rows = self.storage.fetchall(sql, (int(project_id),))
        return {r["kind"]: int(r["n"]) for r in rows}


class LifecycleTransitionRepo(BaseRepo):
    table = "lifecycle_transitions"
    has_updated_at = False

    def list_for_lead(self, lead_id: int, *, limit: int = 200) -> list[dict]:
        return self.find(
            {"lead_id": lead_id},
            order_by="created_at ASC, id ASC",
            limit=limit,
        )

    def latest_for_lead(self, lead_id: int) -> dict | None:
        rows = self.find(
            {"lead_id": lead_id},
            order_by="created_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None


class ScoringWeightRevisionRepo(BaseRepo):
    table = "scoring_weight_revisions"
    json_fields = (
        "proposed_weights", "baseline_weights",
        "contributing_event_ids", "stats",
    )

    def list_for_icp(self, icp_id: int, *, limit: int = 200) -> list[dict]:
        return self.find(
            {"icp_id": int(icp_id)},
            order_by="created_at DESC, id DESC",
            limit=limit,
        )

    def get_active_for_icp(self, icp_id: int) -> dict | None:
        rows = self.find(
            {"icp_id": int(icp_id), "status": "active"},
            order_by="activated_at DESC, id DESC",
            limit=1,
        )
        return rows[0] if rows else None

    def list_proposed_for_icp(self, icp_id: int, *, limit: int = 50) -> list[dict]:
        return self.find(
            {"icp_id": int(icp_id), "status": "proposed"},
            order_by="created_at DESC, id DESC",
            limit=limit,
        )


class PipelineTemplateRepo(BaseRepo):
    table = "pipeline_templates"
    json_fields = ("steps",)

    def list_for_project(self, project_id: int | None, *, status: str | None = None,
                         include_global: bool = True, limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM pipeline_templates WHERE 1=1"
        params: list = []
        if project_id is None:
            sql += " AND project_id IS NULL"
        elif include_global:
            sql += " AND (project_id = ? OR project_id IS NULL)"
            params.append(int(project_id))
        else:
            sql += " AND project_id = ?"
            params.append(int(project_id))
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        rows = self.storage.fetchall(sql, tuple(params))
        return self._decode_many([dict(r) for r in rows])

    def get_by_slug(self, slug: str, *, project_id: int | None = None,
                    status: str | None = "active") -> dict | None:
        query: dict = {"slug": slug}
        if project_id is not None:
            query["project_id"] = int(project_id)
        else:
            # Distinct lookup: prefer project-scoped over global if project_id given.
            pass
        if status:
            query["status"] = status
        rows = self.find(query, order_by="version DESC, id DESC", limit=1)
        return rows[0] if rows else None

    def latest_version(self, *, project_id: int | None, slug: str) -> int:
        rows = self.storage.fetchall(
            "SELECT MAX(version) AS v FROM pipeline_templates "
            "WHERE slug = ? AND COALESCE(project_id, 0) = ?",
            (slug, int(project_id) if project_id is not None else 0),
        )
        if not rows:
            return 0
        v = rows[0]["v"]
        return int(v) if v is not None else 0


class PipelineScheduleRepo(BaseRepo):
    table = "pipeline_schedules"

    def list_for_project(self, project_id: int, *, limit: int = 200) -> list[dict]:
        return self.find(
            {"project_id": int(project_id)},
            order_by="created_at DESC, id DESC",
            limit=limit,
        )

    def list_due(self, *, now_iso_str: str, limit: int = 100) -> list[dict]:
        rows = self.storage.fetchall(
            "SELECT * FROM pipeline_schedules WHERE enabled = 1 "
            "AND next_fire_at IS NOT NULL AND next_fire_at <= ? "
            "ORDER BY next_fire_at ASC LIMIT ?",
            (now_iso_str, int(limit)),
        )
        return self._decode_many([dict(r) for r in rows])


# ============================================================================
# File 23 — Conversation layer
# ============================================================================

class DecisionTraceRepo(BaseRepo):
    table = "decision_traces"
    json_fields = ("input_snapshot",)
    has_updated_at = False

    def list_for_run(self, pipeline_run_id: int, *, limit: int = 500) -> list[dict]:
        return self.find(
            {"pipeline_run_id": pipeline_run_id},
            order_by="created_at ASC, id ASC",
            limit=limit,
        )

    def list_for_lead(self, lead_id: int, *, limit: int = 200) -> list[dict]:
        return self.find(
            {"lead_id": lead_id},
            order_by="created_at DESC, id DESC",
            limit=limit,
        )

    def query(
        self,
        *,
        run_id: int | None = None,
        lead_id: int | None = None,
        contact_id: int | None = None,
        decision_type: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        wheres: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            wheres.append("pipeline_run_id = ?")
            params.append(int(run_id))
        if lead_id is not None:
            wheres.append("lead_id = ?")
            params.append(int(lead_id))
        if contact_id is not None:
            wheres.append("contact_id = ?")
            params.append(int(contact_id))
        if decision_type:
            wheres.append("decision_type = ?")
            params.append(decision_type)
        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        sql = (
            f"SELECT * FROM decision_traces {where_sql} "
            f"ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        params.append(int(limit))
        return self._decode_many(self.storage.fetchall(sql, tuple(params)))


class LeadThreadRepo(BaseRepo):
    table = "lead_threads"

    def find_for_project(
        self,
        project_id: int,
        *,
        status: str | None = None,
        contact_id: int | None = None,
        lead_id: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        where: dict = {"project_id": int(project_id)}
        if status:
            where["status"] = status
        if contact_id is not None:
            where["contact_id"] = int(contact_id)
        if lead_id is not None:
            where["lead_id"] = int(lead_id)
        return self.find(where, order_by="last_message_at DESC, id DESC", limit=limit)

    def find_awaiting_reply(self, project_id: int, *, limit: int = 200) -> list[dict]:
        """Threads where last direction was 'in' and status awaiting_reply."""
        rows = self.storage.fetchall(
            "SELECT * FROM lead_threads WHERE project_id = ? "
            "AND status = 'awaiting_reply' AND last_direction = 'in' "
            "ORDER BY last_message_at ASC LIMIT ?",
            (int(project_id), int(limit)),
        )
        return self._decode_many([dict(r) for r in rows])

    def get_by_contact(self, project_id: int, contact_id: int) -> dict | None:
        return self.find_one({"project_id": project_id, "contact_id": contact_id})

    def increment_message_count(self, thread_id: int) -> None:
        self.storage.execute(
            "UPDATE lead_threads SET message_count = message_count + 1, "
            "updated_at = ? WHERE id = ?",
            (now_iso(), int(thread_id)),
        )

    def touch(self, thread_id: int, *, last_direction: str, last_message_at: str) -> None:
        self.storage.execute(
            "UPDATE lead_threads SET last_direction = ?, last_message_at = ?, "
            "message_count = message_count + 1, updated_at = ? WHERE id = ?",
            (last_direction, last_message_at, now_iso(), int(thread_id)),
        )


class LeadThreadMessageRepo(BaseRepo):
    table = "lead_thread_messages"
    json_fields = ("headers", "attachments", "raw_data")
    has_updated_at = False

    def list_for_thread(self, thread_id: int, *, limit: int = 200) -> list[dict]:
        return self.find(
            {"thread_id": thread_id},
            order_by="COALESCE(sent_at, received_at, created_at) ASC, id ASC",
            limit=limit,
        )

    def latest_for_thread(self, thread_id: int) -> dict | None:
        rows = self.storage.fetchall(
            "SELECT * FROM lead_thread_messages WHERE thread_id = ? "
            "ORDER BY COALESCE(sent_at, received_at, created_at) DESC, id DESC LIMIT 1",
            (int(thread_id),),
        )
        return self._decode(rows[0]) if rows else None

    def has_recent_draft(self, thread_id: int, *, since_iso: str) -> bool:
        rows = self.storage.fetchall(
            "SELECT id FROM lead_thread_messages WHERE thread_id = ? "
            "AND source = 'reply_draft' AND created_at >= ? LIMIT 1",
            (int(thread_id), since_iso),
        )
        return bool(rows)


# ============================================================================
# File 24 — Auth layer
# ============================================================================
class UserRepo(BaseRepo):
    table = "users"

    def get_by_email(self, email: str) -> dict | None:
        return self.find_one({"email": email.strip().lower()})

    def touch_login(self, user_id: int) -> None:
        self.update(user_id, {"last_login_at": now_iso()})


class ProjectMemberRepo(BaseRepo):
    table = "project_members"

    def list_for_user(self, user_id: int) -> list[dict]:
        return self.find({"user_id": user_id})

    def list_for_project(self, project_id: int) -> list[dict]:
        return self.find({"project_id": project_id})

    def get_membership(self, project_id: int, user_id: int) -> dict | None:
        return self.find_one({"project_id": project_id, "user_id": user_id})


class AuditLogRepo(BaseRepo):
    table = "audit_log"
    json_fields = ("metadata",)
    has_updated_at = False

    def list_recent(self, *, project_id: int | None = None, user_id: int | None = None,
                    limit: int = 200) -> list[dict]:
        where: dict = {}
        if project_id:
            where["project_id"] = project_id
        if user_id:
            where["user_id"] = user_id
        return self.find(where, order_by="created_at DESC, id DESC", limit=limit)
