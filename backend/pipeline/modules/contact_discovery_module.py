"""Contact discovery pipeline module.

Wraps services.contact_discovery_service for the pipeline runtime.
Reads ctx.config:
    {
        "sources": [
            {
                "name": "manual",
                "type": "csv",                # optional
                "records": [ { ...raw contact dicts... } ]
            },
            ...
        ]
    }

Each raw contact must include either a `company_id` (already-ingested company)
or a `company_domain` resolvable via CompanyRepo. Records that can't be tied to
a company are skipped with reason 'unknown company'.
"""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.contact_discovery_service import ingest_contact_records


class ContactDiscoveryModule(BaseModule):
    name = "ContactDiscoveryModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        log = ctx.child_logger(self.name)
        cfg = ctx.config or {}
        sources = cfg.get("sources") or []
        if not isinstance(sources, list) or not sources:
            return ModuleResult.ok(
                input_count=0, output_count=0,
                message="no sources provided",
                data={"sources": 0},
            )

        target_personas: list[str] | None = None
        if ctx.icp_id:
            icp = ctx.repos.icps.get(int(ctx.icp_id))
            if icp:
                tp = icp.get("target_personas")
                if isinstance(tp, list):
                    target_personas = [str(x) for x in tp if x]

        totals = {
            "input": 0, "created": 0, "updated": 0, "skipped": 0,
            "leads_created": 0, "leads_updated": 0, "leads_attached": 0,
        }
        by_source: list[dict] = []
        skipped_details: list[dict] = []

        if ctx.dry_run:
            log.info("dry_run_skip", module=self.name, sources=len(sources))
            return ModuleResult.ok(
                input_count=sum(len((s or {}).get("records") or []) for s in sources),
                output_count=0,
                message="dry_run",
                data={"sources": len(sources), "dry_run": True},
            )

        for src in sources:
            if not isinstance(src, dict):
                continue
            name = src.get("name") or "unknown"
            stype = src.get("type") or name
            records = src.get("records") or []
            if not isinstance(records, list):
                continue
            summary = ingest_contact_records(
                ctx.repos,
                project_id=int(ctx.project_id),
                icp_id=int(ctx.icp_id),
                source_name=str(name),
                source_type=str(stype),
                records=records,
                target_personas=target_personas,
            )
            for k in totals:
                totals[k] += int(summary.get(k, 0))
            by_source.append({
                "name": name,
                "input": summary["input"],
                "created": summary["created"],
                "updated": summary["updated"],
                "skipped": summary["skipped"],
            })
            skipped_details.extend(summary.get("skipped_details") or [])

        log.info("contact_discovery_done", **totals)

        return ModuleResult.ok(
            input_count=totals["input"],
            output_count=totals["created"] + totals["updated"],
            failed_count=totals["skipped"],
            message=(
                f"created={totals['created']} updated={totals['updated']} "
                f"skipped={totals['skipped']}"
            ),
            data={
                **totals,
                "by_source": by_source,
                "skipped_details": skipped_details[:20],
            },
        )
