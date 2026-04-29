"""CompanyDiscoveryModule — ingests source records into companies + company_sources."""
from __future__ import annotations

from pipeline.context import PipelineContext
from pipeline.module import BaseModule
from pipeline.result import ModuleResult
from services.company_discovery_service import ingest_company_record


class CompanyDiscoveryModule(BaseModule):
    name = "CompanyDiscoveryModule"

    def execute(self, ctx: PipelineContext) -> ModuleResult:
        sources = ctx.config.get("sources") or []
        if not isinstance(sources, list):
            return ModuleResult.fail("config.sources must be a list")

        total_input = 0
        created = 0
        updated = 0
        failed = 0
        by_source: dict[str, dict] = {}
        skipped_details: list[dict] = []

        for src in sources:
            if not isinstance(src, dict):
                failed += 1
                continue
            source_name = src.get("name") or "manual"
            source_type = src.get("type") or source_name
            records = src.get("records") or []
            stats = {"input": 0, "created": 0, "updated": 0, "skipped": 0}

            for rec in records:
                stats["input"] += 1
                total_input += 1
                if ctx.dry_run:
                    continue
                try:
                    res = ingest_company_record(
                        ctx.repos,
                        project_id=ctx.project_id,
                        icp_id=ctx.icp_id,
                        source_name=source_name,
                        source_type=source_type,
                        raw=rec,
                    )
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    skipped_details.append({"reason": f"exception: {e}", "source": source_name})
                    continue
                action = res.get("action")
                if action == "created":
                    created += 1
                    stats["created"] += 1
                elif action == "updated":
                    updated += 1
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
                    skipped_details.append({
                        "reason": res.get("reason", "skipped"),
                        "source": source_name,
                    })

            by_source[source_name] = stats

        msg = (
            f"sources={len(sources)} input={total_input} created={created} "
            f"updated={updated} skipped={len(skipped_details)} failed={failed}"
        )
        return ModuleResult.ok(
            input_count=total_input,
            output_count=created + updated,
            failed_count=failed,
            message=msg,
            data={
                "created": created,
                "updated": updated,
                "skipped": len(skipped_details),
                "by_source": by_source,
                "skipped_details": skipped_details[:20],
            },
        )
