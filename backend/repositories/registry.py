"""Repository registry. One instance, all repos as attributes."""
from __future__ import annotations

from db.sqlite_storage import SQLiteStorage
from repositories.repos import (
    AuditLogRepo, CampaignEventRepo, CampaignRepo, CompanyEnrichmentRepo, CompanyRepo,
    CompanySourceRepo, ContactEnrichmentRepo, ContactRepo, ContactSourceRepo,
    DecisionTraceRepo, DraftQualityCheckRepo, EmailDraftRepo, EngagementSnapshotRepo,
    ExportRepo, FeedbackEventRepo, ICPRepo,
    KnowledgeRepo, LeadCandidateRepo, LeadExportItemRepo, LeadExportRepo, LeadResearchRepo,
    LeadThreadMessageRepo, LeadThreadRepo,
    LeadVariantAssignmentRepo, LifecycleTransitionRepo, ModuleLogRepo, OutreachExperimentRepo,
    OutreachMessageRepo, OutreachReplyRepo,
    OutreachSendRepo, OutreachVariantRepo, PipelineRunRepo, PipelineRunStepRepo,
    PipelineScheduleRepo, PipelineTemplateRepo,
    ProjectMemberRepo, ProjectRepo, QualityCheckRepo, ScoringWeightRevisionRepo,
    SignalEvidenceRepo, SignalRepo, SuppressionRepo, UserRepo,
)


class RepoRegistry:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

        self.projects = ProjectRepo(storage)
        self.icps = ICPRepo(storage)

        self.companies = CompanyRepo(storage)
        self.company_sources = CompanySourceRepo(storage)
        self.company_enrichment = CompanyEnrichmentRepo(storage)

        self.contacts = ContactRepo(storage)
        self.contact_sources = ContactSourceRepo(storage)
        self.contact_enrichment = ContactEnrichmentRepo(storage)

        self.signals = SignalRepo(storage)
        self.signal_evidence = SignalEvidenceRepo(storage)

        self.lead_candidates = LeadCandidateRepo(storage)
        self.lead_research = LeadResearchRepo(storage)

        self.email_drafts = EmailDraftRepo(storage)
        self.draft_quality_checks = DraftQualityCheckRepo(storage)
        self.outreach_messages = OutreachMessageRepo(storage)
        self.quality_checks = QualityCheckRepo(storage)
        self.outreach_sends = OutreachSendRepo(storage)
        self.outreach_replies = OutreachReplyRepo(storage)
        self.engagement_snapshots = EngagementSnapshotRepo(storage)

        self.outreach_experiments = OutreachExperimentRepo(storage)
        self.outreach_variants = OutreachVariantRepo(storage)
        self.lead_variant_assignments = LeadVariantAssignmentRepo(storage)

        self.lead_exports = LeadExportRepo(storage)
        self.lead_export_items = LeadExportItemRepo(storage)

        self.feedback_events = FeedbackEventRepo(storage)
        self.lifecycle_transitions = LifecycleTransitionRepo(storage)
        self.scoring_weight_revisions = ScoringWeightRevisionRepo(storage)

        self.suppression = SuppressionRepo(storage)
        self.knowledge = KnowledgeRepo(storage)

        self.pipeline_runs = PipelineRunRepo(storage)
        self.pipeline_run_steps = PipelineRunStepRepo(storage)
        self.pipeline_templates = PipelineTemplateRepo(storage)
        self.pipeline_schedules = PipelineScheduleRepo(storage)
        self.module_logs = ModuleLogRepo(storage)

        self.exports = ExportRepo(storage)

        self.campaigns = CampaignRepo(storage)
        self.campaign_events = CampaignEventRepo(storage)

        # File 23 — conversation layer
        self.decision_traces = DecisionTraceRepo(storage)
        self.lead_threads = LeadThreadRepo(storage)
        self.lead_thread_messages = LeadThreadMessageRepo(storage)

        # File 24 — auth layer
        self.users = UserRepo(storage)
        self.project_members = ProjectMemberRepo(storage)
        self.audit_log = AuditLogRepo(storage)
