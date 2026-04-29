"""PipelineRegistry: run_type -> ordered list of module classes."""
from __future__ import annotations

from typing import Type

from pipeline.module import DummyEchoModule, PipelineModule


# All slots from File 03 §3.6. Real modules are registered in later phases.
RUN_TYPES = (
    "company_discovery",
    "company_enrichment",
    "contact_discovery",
    "contact_enrichment",
    "suppression",
    "signal_extraction",
    "scoring",
    "lead_scoring",
    "outreach_generation",
    "deduplication",
    "research",
    "email_drafts",
    "quality_control",
    "send_queue",
    "reply_tracking",
    "engagement_metrics",
    "experiment_scoring",
    "export",
    "feedback_ingestion",
    "weight_tuning",
    "reply_drafter",
    "full_pipeline",
)


class PipelineRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, list[Type[PipelineModule]]] = {rt: [] for rt in RUN_TYPES}

    def register(self, run_type: str, module_classes: list[Type[PipelineModule]]) -> None:
        if run_type not in self._registry:
            self._registry[run_type] = []
        self._registry[run_type] = list(module_classes)

    def append(self, run_type: str, module_class: Type[PipelineModule]) -> None:
        self._registry.setdefault(run_type, []).append(module_class)

    def get(self, run_type: str) -> list[Type[PipelineModule]]:
        return list(self._registry.get(run_type, []))

    def known_run_types(self) -> list[str]:
        return list(self._registry.keys())


# Default registry shared by the runner. Real modules are added in later phases.
default_registry = PipelineRegistry()
default_registry.register("full_pipeline", [DummyEchoModule])

# Lazy register concrete modules to avoid circular imports during module load.
def _register_default_modules() -> None:
    from pipeline.modules.company_discovery_module import CompanyDiscoveryModule
    from pipeline.modules.company_enrichment_module import CompanyEnrichmentModule
    from pipeline.modules.contact_discovery_module import ContactDiscoveryModule
    from pipeline.modules.contact_enrichment_module import ContactEnrichmentModule
    from pipeline.modules.engagement_metrics_module import EngagementMetricsModule
    from pipeline.modules.experiment_scoring_module import ExperimentScoringModule
    from pipeline.modules.export_module import ExportModule
    from pipeline.modules.feedback_ingestion_module import FeedbackIngestionModule
    from pipeline.modules.lead_scoring_module import LeadScoringModule
    from pipeline.modules.outreach_generation_module import OutreachGenerationModule
    from pipeline.modules.quality_control_module import QualityControlModule
    from pipeline.modules.reply_tracking_module import ReplyTrackingModule
    from pipeline.modules.send_module import SendModule
    from pipeline.modules.signal_extraction_module import SignalExtractionModule
    from pipeline.modules.suppression_module import SuppressionModule
    from pipeline.modules.weight_tuning_module import WeightTuningModule

    default_registry.register("company_discovery", [CompanyDiscoveryModule])
    default_registry.register("company_enrichment", [CompanyEnrichmentModule])
    default_registry.register("contact_discovery", [ContactDiscoveryModule])
    default_registry.register("contact_enrichment", [ContactEnrichmentModule])
    default_registry.register("suppression", [SuppressionModule])
    default_registry.register("signal_extraction", [SignalExtractionModule])
    default_registry.register("lead_scoring", [LeadScoringModule])
    default_registry.register("outreach_generation", [OutreachGenerationModule])
    default_registry.register("quality_control", [QualityControlModule])
    default_registry.register("send_queue", [SendModule])
    default_registry.register("reply_tracking", [ReplyTrackingModule])
    default_registry.register("engagement_metrics", [EngagementMetricsModule])
    default_registry.register("experiment_scoring", [ExperimentScoringModule])
    default_registry.register("export", [ExportModule])
    default_registry.register("feedback_ingestion", [FeedbackIngestionModule])
    default_registry.register("weight_tuning", [WeightTuningModule])

    from pipeline.modules.multi_turn_drafter_module import MultiTurnDrafterModule
    default_registry.register("reply_drafter", [MultiTurnDrafterModule])

    # full_pipeline is template-driven (File 22). The FullPipelineModule resolves
    # a pipeline_templates row and dispatches each step via PipelineRunner.run_now.
    from pipeline.modules.full_pipeline_module import FullPipelineModule
    default_registry.register("full_pipeline", [FullPipelineModule])


_register_default_modules()
