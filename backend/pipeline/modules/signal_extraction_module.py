"""SignalExtractionModule — extract signals for project's companies & contacts.

ctx.config:
    {
        "company_ids": [int, ...],
        "contact_ids": [int, ...],
        "company_id": int,
        "signal_types": ["hiring_intent", ...],
        "limit": 100,
        "only_missing": True,
    }
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.signal_extraction_service import run_signals_batch


class SignalExtractionModule(BaseModule):
    name = "SignalExtractionModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        company_ids = cfg.get("company_ids") or None
        contact_ids = cfg.get("contact_ids") or None
        company_id = cfg.get("company_id")
        signal_types = cfg.get("signal_types") or None
        limit = int(cfg.get("limit") or 100)
        only_missing = bool(cfg.get("only_missing", True))

        result = run_signals_batch(
            ctx.repos,
            project_id=int(ctx.project_id) if ctx.project_id and not (company_ids or contact_ids or company_id) else None,
            company_id=int(company_id) if company_id is not None else None,
            company_ids=[int(x) for x in company_ids] if company_ids else None,
            contact_ids=[int(x) for x in contact_ids] if contact_ids else None,
            signal_types=signal_types,
            icp_id=int(ctx.icp_id) if ctx.icp_id else None,
            limit=limit,
            only_missing=only_missing,
            dry_run=ctx.dry_run,
            detected_by="pipeline",
        )

        log.info(
            "signal_extraction_done",
            scanned_companies=result["scanned_companies"],
            scanned_contacts=result["scanned_contacts"],
            persisted=result["persisted"],
            failed=result["failed"],
        )

        return ModuleResult.ok(
            input_count=result["scanned_companies"] + result["scanned_contacts"],
            output_count=result["persisted"],
            failed_count=result["failed"],
            message=(
                f"persisted={result['persisted']} "
                f"companies={result['scanned_companies']} "
                f"contacts={result['scanned_contacts']} "
                f"failed={result['failed']}"
            ),
            data={
                "scanned_companies": result["scanned_companies"],
                "scanned_contacts": result["scanned_contacts"],
                "persisted": result["persisted"],
                "failed": result["failed"],
            },
        )
