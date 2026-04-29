import axios, { AxiosError } from "axios";

const baseURL =
  (import.meta.env.VITE_API_BASE as string | undefined) ||
  "http://127.0.0.1:5214";

export const AUTH_TOKEN_KEY = "gtm.authToken";

export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((cfg) => {
  const t =
    typeof window !== "undefined" ? localStorage.getItem(AUTH_TOKEN_KEY) : null;
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export type ApiError = { message: string; status?: number; detail?: unknown };

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError<{ detail?: string }>) => {
    const status = err.response?.status;
    if (status === 401 && typeof window !== "undefined") {
      // Clear stale token; ProtectedRoute will redirect to /login
      localStorage.removeItem(AUTH_TOKEN_KEY);
      if (
        !window.location.pathname.startsWith("/login") &&
        !window.location.pathname.startsWith("/register")
      ) {
        window.location.assign("/login");
      }
    }
    const e: ApiError = {
      message:
        (err.response?.data as { detail?: string })?.detail ||
        err.message ||
        "Request failed",
      status,
      detail: err.response?.data,
    };
    return Promise.reject(e);
  }
);

// ── Auth types & API ────────────────────────────────────────────────────────
export type AuthUser = {
  id: number;
  email: string;
  full_name: string | null;
  role: "admin" | "user";
  is_active: boolean;
  created_at?: string;
  last_login_at?: string | null;
};

export type AuthMembership = {
  id: number;
  project_id: number;
  user_id: number;
  role: "owner" | "admin" | "member" | "viewer";
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export const authApi = {
  register: (body: { email: string; password: string; full_name?: string }) =>
    api.post<AuthResponse>("/auth/register", body).then((r) => r.data),
  login: (body: { email: string; password: string }) =>
    api.post<AuthResponse>("/auth/login", body).then((r) => r.data),
  me: () =>
    api
      .get<{ user: AuthUser; memberships: AuthMembership[] }>("/auth/me")
      .then((r) => r.data),
  changePassword: (body: { old_password: string; new_password: string }) =>
    api.post<{ ok: boolean }>("/auth/change-password", body).then((r) => r.data),
};

// Typed helpers
export type Project = { id: number; name: string; created_at?: string };
export type PipelineRun = {
  id: number;
  project_id: number;
  icp_id: number | null;
  run_type: string;
  status: "running" | "completed" | "partially_completed" | "failed" | "skipped";
  started_at: string;
  finished_at: string | null;
  total_processed: number;
  total_created: number;
  total_failed: number;
  config: Record<string, unknown>;
  error_message: string | null;
};
export type PipelineStep = {
  id: number;
  pipeline_run_id: number;
  module_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  input_count: number;
  output_count: number;
  failed_count: number;
  error_message: string | null;
  result_data: Record<string, unknown>;
};
export type ModuleLog = {
  id: number;
  pipeline_run_id: number;
  pipeline_run_step_id: number | null;
  module_name: string;
  level: string;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
};

export const projectsApi = {
  list: () => api.get<{ data: Project[] }>("/projects").then((r) => r.data.data),
  create: (name: string) =>
    api.post<Project>("/projects", { name }).then((r) => r.data),
};

export const pipelineApi = {
  listRuns: (projectId: number, limit = 50) =>
    api
      .get<{ data: PipelineRun[] }>("/pipeline/runs", {
        params: { project_id: projectId, limit },
      })
      .then((r) => r.data.data),
  getRun: (runId: number) =>
    api
      .get<{ run: PipelineRun; steps: PipelineStep[]; logs: ModuleLog[] }>(
        `/pipeline/runs/${runId}`
      )
      .then((r) => r.data),
  createRun: (body: {
    project_id: number;
    icp_id?: number | null;
    run_type: string;
    config?: Record<string, unknown>;
    dry_run?: boolean;
  }) =>
    api
      .post<{ pipeline_run_id: number }>("/pipeline/runs", body)
      .then((r) => r.data),
  runTypes: () =>
    api
      .get<{ run_types: string[] }>("/pipeline/run-types")
      .then((r) => r.data.run_types),
};

export type ICPStatus = "draft" | "active" | "archived";

export type ICP = {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  target_industries: string[] | null;
  target_roles: string[] | null;
  target_geographies: string[] | null;
  target_seniorities: string[] | null;
  target_personas: string[] | null;
  target_company_sizes: string[] | null;
  target_company_size_min: number | null;
  target_company_size_max: number | null;
  target_revenue_range: string | null;
  pain_points: string[] | null;
  competitors: string[] | null;
  buying_signals: string[] | null;
  exclusion_rules: Record<string, unknown> | null;
  offer_summary: string | null;
  value_proposition: string | null;
  outreach_angle: string | null;
  status: ICPStatus;
  created_at: string;
  updated_at: string;
};

export type ICPSummary = {
  icp_id: number;
  companies_targeted: number;
  contacts_targeted: number;
  leads_total: number;
  leads_ready: number;
  drafts_total: number;
  drafts_pending: number;
  signals_total: number;
};

export type ICPPayload = Partial<Omit<ICP, "id" | "created_at" | "updated_at">> & {
  project_id?: number;
  exclusion_criteria?: string | Record<string, unknown> | null;
  target_buying_signals?: string[];
};

export const icpsApi = {
  list: (projectId: number, status?: ICPStatus) =>
    api
      .get<{ data: ICP[] }>("/icps", { params: { project_id: projectId, status } })
      .then((r) => r.data.data),
  get: (id: number) => api.get<ICP>(`/icps/${id}`).then((r) => r.data),
  create: (payload: ICPPayload) =>
    api.post<ICP>("/icps", payload).then((r) => r.data),
  update: (id: number, payload: ICPPayload) =>
    api.patch<ICP>(`/icps/${id}`, payload).then((r) => r.data),
  activate: (id: number) =>
    api.post<ICP>(`/icps/${id}/activate`).then((r) => r.data),
  archive: (id: number) =>
    api.post<ICP>(`/icps/${id}/archive`).then((r) => r.data),
  clone: (id: number, name?: string) =>
    api.post<ICP>(`/icps/${id}/clone`, name ? { name } : {}).then((r) => r.data),
  summary: (id: number) =>
    api.get<ICPSummary>(`/icps/${id}/summary`).then((r) => r.data),
};

export type Company = {
  id: number;
  name: string | null;
  domain: string | null;
  website_url: string | null;
  linkedin_url: string | null;
  country: string | null;
  city: string | null;
  industry: string | null;
  description: string | null;
  employee_count: number | null;
  revenue_estimate: string | null;
  ecommerce_platform: string | null;
  tech_stack: string[] | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type CompanySource = {
  id: number;
  company_id: number;
  source_type: string;
  source_name: string | null;
  source_url: string | null;
  raw_data: Record<string, unknown> | null;
  confidence_score: number | null;
  discovered_at: string;
};

export type CompanyIngestSummary = {
  input: number;
  created: number;
  updated: number;
  skipped: number;
  skipped_details: { reason: string; record: Record<string, unknown> }[];
};

export const companiesApi = {
  list: (projectId: number, status?: string, limit = 200) =>
    api
      .get<{ data: Company[] }>("/companies", {
        params: { project_id: projectId, status, limit },
      })
      .then((r) => r.data.data),
  get: (id: number) =>
    api
      .get<{ company: Company; sources: CompanySource[] }>(`/companies/${id}`)
      .then((r) => r.data),
  ingest: (params: {
    projectId: number;
    icpId?: number | null;
    sourceName: string;
    sourceType?: string;
    records: Record<string, unknown>[];
  }) =>
    api
      .post<CompanyIngestSummary>("/companies/ingest", {
        project_id: params.projectId,
        icp_id: params.icpId ?? null,
        source_name: params.sourceName,
        source_type: params.sourceType ?? params.sourceName,
        records: params.records,
      })
      .then((r) => r.data),
};

export type Contact = {
  id: number;
  company_id: number;
  first_name: string | null;
  last_name: string | null;
  full_name: string | null;
  job_title: string | null;
  normalized_role: string | null;
  email: string | null;
  email_status: string | null;
  email_confidence: number | null;
  linkedin_url: string | null;
  country: string | null;
  city: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ContactSource = {
  id: number;
  contact_id: number;
  source_type: string;
  source_name: string | null;
  source_url: string | null;
  raw_data: Record<string, unknown> | null;
  confidence_score: number | null;
  discovered_at: string;
};

export type LeadCandidate = {
  id: number;
  project_id: number;
  icp_id: number;
  company_id: number;
  contact_id: number | null;
  lead_status: string;
  final_score: number | null;
  ready_for_outreach: number;
  created_at: string;
  updated_at: string;
};

export type ContactIngestSummary = {
  input: number;
  created: number;
  updated: number;
  skipped: number;
  skipped_details: { reason: string; record: Record<string, unknown> }[];
  leads_created: number;
  leads_updated: number;
  leads_attached: number;
};

export const contactsApi = {
  list: (projectId: number, opts?: { companyId?: number; role?: string; limit?: number }) =>
    api
      .get<{ data: Contact[] }>("/contacts", {
        params: {
          project_id: projectId,
          company_id: opts?.companyId,
          role: opts?.role,
          limit: opts?.limit ?? 200,
        },
      })
      .then((r) => r.data.data),
  get: (id: number) =>
    api
      .get<{ contact: Contact; sources: ContactSource[]; leads: LeadCandidate[] }>(
        `/contacts/${id}`,
      )
      .then((r) => r.data),
  ingest: (params: {
    projectId: number;
    icpId: number;
    sourceName: string;
    sourceType?: string;
    records: Record<string, unknown>[];
  }) =>
    api
      .post<ContactIngestSummary>("/contacts/ingest", {
        project_id: params.projectId,
        icp_id: params.icpId,
        source_name: params.sourceName,
        source_type: params.sourceType ?? params.sourceName,
        records: params.records,
      })
      .then((r) => r.data),
};

export const healthApi = {
  base: () =>
    api.get<{ status: string; db: boolean; env: string }>("/health").then((r) => r.data),
  db: () =>
    api
      .get<{ db_path: string; schema_version: string }>("/health/db")
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Suppression (File 08)
// ---------------------------------------------------------------------------
export type SuppressionType =
  | "domain"
  | "email"
  | "company_name"
  | "linkedin_url"
  | "competitor"
  | "customer"
  | "unsubscribed"
  | "bounced";

export type SuppressionEntry = {
  id: number;
  suppression_type: SuppressionType;
  value: string;
  reason: string | null;
  source: string | null;
  created_at: string;
};

export type SuppressionListResponse = {
  data: SuppressionEntry[];
  total: number;
  stats: Record<string, number>;
};

export type SuppressionImportSummary = {
  input: number;
  created: number;
  existing: number;
  skipped: number;
  invalid: number;
};

export type SuppressionApplyResult = {
  scanned: number;
  suppressed: number;
  by_reason: Record<string, number>;
  lead_ids: number[];
  dry_run: boolean;
};

export const suppressionApi = {
  list: (opts?: { type?: SuppressionType; q?: string; limit?: number; offset?: number }) =>
    api
      .get<SuppressionListResponse>("/suppression", {
        params: {
          suppression_type: opts?.type,
          q: opts?.q,
          limit: opts?.limit ?? 200,
          offset: opts?.offset ?? 0,
        },
      })
      .then((r) => r.data),
  types: () => api.get<{ types: SuppressionType[] }>("/suppression/types").then((r) => r.data.types),
  add: (entry: { suppression_type: SuppressionType; value: string; reason?: string; source?: string }) =>
    api
      .post<{ id: number; action: "created" | "existing"; entry: SuppressionEntry }>(
        "/suppression",
        entry,
      )
      .then((r) => r.data),
  delete: (id: number) =>
    api.delete<{ deleted: number }>(`/suppression/${id}`).then((r) => r.data),
  bulkImport: (records: { suppression_type: SuppressionType; value: string; reason?: string; source?: string }[]) =>
    api
      .post<SuppressionImportSummary>("/suppression/import", { records })
      .then((r) => r.data),
  apply: (opts?: { project_id?: number; icp_id?: number; dry_run?: boolean }) =>
    api.post<SuppressionApplyResult>("/suppression/apply", opts ?? {}).then((r) => r.data),
};

// ============================================================================
// Company enrichment
// ============================================================================
export type CompanyEnrichmentSnapshot = {
  fetch_url?: string | null;
  status_code?: number | null;
  ok?: boolean;
  error?: string | null;
  title?: string | null;
  description?: string | null;
  og_title?: string | null;
  og_description?: string | null;
  og_image?: string | null;
  og_site_name?: string | null;
  canonical?: string | null;
  language?: string | null;
  tech_stack?: string[];
  ecommerce_platform?: string | null;
  industry?: string | null;
  social_links?: string[];
  text_excerpt?: string;
};

export type CompanyEnrichmentRow = {
  id: number;
  company_id: number;
  provider: string;
  industry: string | null;
  tech_stack: string[] | null;
  ecommerce_platform: string | null;
  social_links: string[] | null;
  raw_data: CompanyEnrichmentSnapshot | null;
  confidence_score: number | null;
  created_at: string;
};

export type EnrichOneResult = {
  company_id: number;
  domain?: string;
  ok: boolean;
  status_code?: number;
  error?: string | null;
  snapshot?: CompanyEnrichmentSnapshot;
  updates?: Record<string, unknown>;
  enrichment_id?: number;
  dry_run?: boolean;
  skipped?: boolean;
};

export type EnrichBatchResult = {
  scanned: number;
  enriched: number;
  skipped: number;
  failed: number;
  results: EnrichOneResult[];
  dry_run: boolean;
};

export const enrichmentApi = {
  enrichCompany: (id: number, dryRun = false) =>
    api
      .post<EnrichOneResult>(`/companies/${id}/enrich`, { dry_run: dryRun })
      .then((r) => r.data),
  getEnrichment: (id: number, limit = 10) =>
    api
      .get<{
        company_id: number;
        latest: CompanyEnrichmentRow | null;
        history: CompanyEnrichmentRow[];
        count: number;
      }>(`/companies/${id}/enrichment`, { params: { limit } })
      .then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    company_ids?: number[];
    limit?: number;
    only_missing?: boolean;
    dry_run?: boolean;
  }) => api.post<EnrichBatchResult>("/enrichment/companies/run", opts).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Contact enrichment (File 10)
// ---------------------------------------------------------------------------
export type ContactEnrichmentSnapshot = {
  provider: string;
  source: string;
  email: string | null;
  email_status: string | null;
  email_confidence: number | null;
  syntax_ok: boolean;
  domain: string | null;
  is_free: boolean;
  is_disposable: boolean;
  is_role: boolean;
  has_mx: boolean | null;
  is_catch_all: boolean | null;
  typo_corrected_from: string | null;
  reason: string;
  raw: Record<string, unknown>;
};

export type ContactEnrichmentRow = {
  id: number;
  contact_id: number;
  provider: string;
  email: string | null;
  email_status: string | null;
  email_confidence: number | null;
  job_title: string | null;
  linkedin_url: string | null;
  phone: string | null;
  raw_data: ContactEnrichmentSnapshot | null;
  created_at: string;
};

export type EnrichContactResult = {
  contact_id: number;
  email: string;
  ok: boolean;
  status: string | null;
  confidence: number | null;
  snapshot: ContactEnrichmentSnapshot;
  enrichment_id?: number;
  updates: Record<string, unknown>;
  dry_run: boolean;
  skipped?: boolean;
  error?: string;
};

export type EnrichContactsBatchResult = {
  scanned: number;
  enriched: number;
  skipped: number;
  failed: number;
  results: EnrichContactResult[];
  dry_run: boolean;
};

export type ImportEnrichedContactsResult = {
  input: number;
  created: number;
  updated: number;
  skipped: number;
  skipped_details: { reason: string; record: Record<string, unknown> }[];
  enriched: number;
  leads_created: number;
  leads_updated: number;
  leads_attached: number;
  results: {
    contact_id: number;
    action: string;
    lead_id: number;
    lead_action: string;
    email_status: string | null;
    email_confidence: number | null;
  }[];
  suppression_reapplied?: { scanned?: number; suppressed?: number; error?: string };
};

export const contactEnrichmentApi = {
  enrichOne: (id: number, opts?: { icpId?: number; dryRun?: boolean }) =>
    api
      .post<EnrichContactResult>(`/contacts/${id}/enrich`, {
        icp_id: opts?.icpId,
        dry_run: opts?.dryRun ?? false,
      })
      .then((r) => r.data),
  getEnrichment: (id: number, limit = 10) =>
    api
      .get<{
        contact_id: number;
        latest: ContactEnrichmentRow | null;
        history: ContactEnrichmentRow[];
        count: number;
      }>(`/contacts/${id}/enrichment`, { params: { limit } })
      .then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    company_id?: number;
    contact_ids?: number[];
    icp_id?: number;
    limit?: number;
    only_missing?: boolean;
    dry_run?: boolean;
  }) =>
    api
      .post<EnrichContactsBatchResult>("/enrichment/contacts/run", opts)
      .then((r) => r.data),
  importCsv: (opts: {
    project_id: number;
    icp_id: number;
    csv?: string;
    records?: Record<string, unknown>[];
    source_name?: string;
  }) =>
    api
      .post<ImportEnrichedContactsResult>("/enrichment/contacts/import", opts)
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Signals (File 11)
// ---------------------------------------------------------------------------

export const SIGNAL_TYPES = [
  "hiring_intent",
  "news_mention",
  "funding",
  "tech_stack_change",
  "hiring_pace",
  "social_activity",
  "role_change",
  "linkedin_activity",
] as const;
export type SignalType = (typeof SIGNAL_TYPES)[number];

export type SignalRow = {
  id: number;
  company_id: number | null;
  contact_id: number | null;
  icp_id: number | null;
  signal_type: SignalType | string;
  signal_name: string | null;
  description: string | null;
  extracted_text: string | null;
  source_url: string | null;
  strength_score: number | null;
  confidence_score: number | null;
  detected_by: string | null;
  raw_data: Record<string, unknown> | null;
  created_at: string;
};

export type SignalsListResult = {
  company_id?: number;
  contact_id?: number;
  count: number;
  data: SignalRow[];
};

export type ExtractSignalsResult = {
  company_id?: number;
  contact_id?: number;
  ok: boolean;
  skipped?: boolean;
  error?: string;
  detected: number;
  persisted: number;
  signals: SignalRow[];
  dry_run: boolean;
};

export type SignalsBatchResult = {
  scanned_companies: number;
  scanned_contacts: number;
  persisted: number;
  failed: number;
  dry_run: boolean;
  company_results: ExtractSignalsResult[];
  contact_results: ExtractSignalsResult[];
};

export const signalsApi = {
  listForCompany: (companyId: number, opts?: { type?: string; limit?: number }) =>
    api
      .get<SignalsListResult>(`/companies/${companyId}/signals`, {
        params: { type: opts?.type, limit: opts?.limit },
      })
      .then((r) => r.data),
  listForContact: (contactId: number, opts?: { type?: string; limit?: number }) =>
    api
      .get<SignalsListResult>(`/contacts/${contactId}/signals`, {
        params: { type: opts?.type, limit: opts?.limit },
      })
      .then((r) => r.data),
  extractForCompany: (companyId: number, body?: Record<string, unknown>) =>
    api
      .post<ExtractSignalsResult>(`/companies/${companyId}/signals/extract`, body ?? {})
      .then((r) => r.data),
  extractForContact: (contactId: number, body?: Record<string, unknown>) =>
    api
      .post<ExtractSignalsResult>(`/contacts/${contactId}/signals/extract`, body ?? {})
      .then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    company_id?: number;
    company_ids?: number[];
    contact_ids?: number[];
    icp_id?: number;
    signal_types?: string[];
    limit?: number;
    only_missing?: boolean;
    dry_run?: boolean;
  }) => api.post<SignalsBatchResult>("/signals/run", opts).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Lead scoring (File 12)
// ---------------------------------------------------------------------------

export const PRIORITY_TIERS = ["A", "B", "C", "D"] as const;
export type PriorityTier = (typeof PRIORITY_TIERS)[number];

export type LeadRow = {
  id: number;
  project_id: number;
  icp_id: number;
  company_id: number;
  contact_id: number | null;
  lead_status: string;
  icp_fit_score: number | null;
  signal_score: number | null;
  final_score: number | null;
  priority_tier: PriorityTier | null;
  scored_at: string | null;
  created_at: string;
  updated_at: string | null;
  company_name: string | null;
  company_domain: string | null;
  company_industry: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;
};

export type LeadsListResult = {
  project_id: number;
  count: number;
  filters: { min_score: number | null; tier: PriorityTier | null; limit: number };
  data: LeadRow[];
};

export type LeadScoringExplanation = {
  scorer?: string;
  fit_ratio?: number;
  intent_ratio?: number;
  fit?: {
    score?: number;
    criteria?: Record<string, {
      matched?: boolean;
      reason?: string;
      weight?: number;
      score?: number;
      [k: string]: unknown;
    }>;
    matched?: string[];
    missed?: string[];
  };
  intent?: {
    score?: number;
    signal_count?: number;
    halflife_days?: number;
    contributions?: Array<{
      signal_id?: number;
      signal_type?: string;
      weight?: number;
      strength?: number;
      recency?: number;
      contribution?: number;
    }>;
  };
  combined?: number;
  tier?: PriorityTier;
  llm?: { nudge?: number; reason?: string };
  note?: string;
  [k: string]: unknown;
};

export type LeadScoreResult = {
  lead_id: number;
  ok: boolean;
  error?: string;
  fit_score?: number;
  intent_score?: number;
  combined_score?: number;
  priority_tier?: PriorityTier;
  scored_at?: string;
  scoring_explanation?: LeadScoringExplanation;
  persisted?: boolean;
  signal_count?: number;
};

export type ScoringBatchResult = {
  scanned: number;
  scored: number;
  persisted: number;
  failed: number;
  tier_counts: Record<PriorityTier, number>;
  lead_ids: number[];
  dry_run: boolean;
};

export type LeadScoringDetail = {
  lead_id: number;
  fit_score: number | null;
  intent_score: number | null;
  combined_score: number | null;
  priority_tier: PriorityTier | null;
  scored_at: string | null;
  lead_status: string | null;
  scoring_explanation: LeadScoringExplanation | null;
};

export const leadsApi = {
  scoreLead: (leadId: number, body?: { dry_run?: boolean }) =>
    api.post<LeadScoreResult>(`/leads/${leadId}/score`, body ?? {}).then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    icp_id?: number;
    lead_ids?: number[];
    only_missing?: boolean;
    dry_run?: boolean;
    limit?: number;
  }) => api.post<ScoringBatchResult>("/scoring/run", opts).then((r) => r.data),
  list: (opts: {
    project_id: number;
    min_score?: number;
    tier?: PriorityTier;
    limit?: number;
  }) =>
    api
      .get<LeadsListResult>("/leads", {
        params: {
          project_id: opts.project_id,
          min_score: opts.min_score,
          tier: opts.tier,
          limit: opts.limit,
        },
      })
      .then((r) => r.data),
  getScoring: (leadId: number) =>
    api.get<LeadScoringDetail>(`/leads/${leadId}/scoring`).then((r) => r.data),
};

// ---------- Outreach (File 13) ----------

export const OUTREACH_STATUSES = ["draft", "approved", "sent"] as const;
export type OutreachStatus = (typeof OUTREACH_STATUSES)[number];

export type OutreachSignalContribution = {
  signal_type?: string | null;
  strength?: number | null;
  recency?: number | null;
  contribution?: number | null;
  weight?: number | null;
};

export type OutreachContext = {
  signals_top?: OutreachSignalContribution[];
  matched_criteria?: string[];
  channel?: string;
};

export type OutreachMessage = {
  id: number;
  lead_id: number;
  channel: string;
  subject: string | null;
  body: string | null;
  body_html: string | null;
  status: OutreachStatus;
  model: string | null;
  prompt: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  context: OutreachContext | null;
  raw_response: Record<string, unknown> | null;
  generated_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  created_at?: string;
  updated_at?: string;
};

export type OutreachListRow = {
  id: number;
  lead_id: number;
  channel: string;
  subject: string | null;
  body: string | null;
  body_html: string | null;
  status: OutreachStatus;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  generated_at: string | null;
  approved_at: string | null;
  sent_at: string | null;
  priority_tier: PriorityTier | null;
  final_score: number | null;
  company_name: string | null;
  company_domain: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;
};

export type OutreachListResult = {
  project_id: number;
  count: number;
  filters: { status: OutreachStatus | null; min_tier: PriorityTier | null; limit: number };
  data: OutreachListRow[];
};

export type OutreachLeadHistory = {
  lead_id: number;
  count: number;
  latest: OutreachMessage | null;
  history: OutreachMessage[];
};

export type OutreachGenerateResult = {
  lead_id: number;
  ok: boolean;
  error?: string;
  message_id: number | null;
  subject: string | null;
  body: string | null;
  body_html: string | null;
  model: string | null;
  status: OutreachStatus;
  channel: string;
  prompt_tokens: number;
  completion_tokens: number;
  generated_at: string | null;
  persisted: boolean;
  context: OutreachContext | null;
  prompt: string | null;
  tier: PriorityTier | null;
  signal_count: number;
};

export type OutreachBatchItem = {
  lead_id: number;
  message_id: number | null;
  subject: string | null;
  ok?: boolean;
  error?: string;
};

export type OutreachBatchResult = {
  scanned: number;
  generated: number;
  persisted: number;
  failed: number;
  skipped_below_tier: number;
  skipped_existing: number;
  min_tier: PriorityTier;
  channel: string;
  dry_run: boolean;
  lead_ids: number[];
  items: OutreachBatchItem[];
};

export const outreachApi = {
  generate: (leadId: number, body?: { dry_run?: boolean; channel?: string }) =>
    api.post<OutreachGenerateResult>(`/leads/${leadId}/outreach/generate`, body ?? {}).then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    icp_id?: number;
    lead_ids?: number[];
    only_missing?: boolean;
    dry_run?: boolean;
    limit?: number;
    min_tier?: PriorityTier;
    channel?: string;
  }) => api.post<OutreachBatchResult>("/outreach/run", opts).then((r) => r.data),
  getForLead: (leadId: number, limit = 20) =>
    api.get<OutreachLeadHistory>(`/leads/${leadId}/outreach`, { params: { limit } }).then((r) => r.data),
  list: (opts: {
    project_id: number;
    status?: OutreachStatus;
    min_tier?: PriorityTier;
    limit?: number;
  }) =>
    api.get<OutreachListResult>("/outreach", {
      params: {
        project_id: opts.project_id,
        status: opts.status,
        min_tier: opts.min_tier,
        limit: opts.limit,
      },
    }).then((r) => r.data),
  approve: (messageId: number, body?: { force?: boolean }) =>
    api.post<{ ok: boolean; message_id: number; status: OutreachStatus; forced?: boolean }>(
      `/outreach/${messageId}/approve`,
      body ?? {},
    ).then((r) => r.data),
  edit: (messageId: number, body: { subject?: string; body?: string; body_html?: string }) =>
    api.post<{ ok: boolean; message_id: number; message: OutreachMessage }>(
      `/outreach/${messageId}/edit`,
      body,
    ).then((r) => r.data),
};

// ---------- Quality control (File 14) ----------

export const QUALITY_RULES = [
  "subject_length",
  "body_word_count",
  "merge_tags",
  "pii",
  "suppression",
  "spam_words",
] as const;
export type QualityRule = (typeof QUALITY_RULES)[number];

export type QualityRuleResult = {
  rule: QualityRule | string;
  passed: boolean;
  reason: string;
  severity?: "info" | "warn" | "critical" | string;
  weight?: number;
};

export type QualityCheck = {
  id: number;
  outreach_message_id: number;
  checker: string;
  score: number;
  passed: number; // 0/1 from sqlite
  rule_results: QualityRuleResult[] | null;
  created_at: string;
};

export type QualityCheckResponse = {
  message_id: number;
  ok: boolean;
  error?: string;
  check_id: number | null;
  checker: string;
  score: number;
  passed: boolean;
  rule_results: QualityRuleResult[];
  created_at: string;
  persisted: boolean;
};

export type QualityMessageHistory = {
  message_id: number;
  count: number;
  latest: QualityCheck | null;
  history: QualityCheck[];
};

export type QualityListRow = QualityCheck & {
  subject: string | null;
  message_status: OutreachStatus;
  lead_id: number;
  priority_tier: PriorityTier | null;
  final_score: number | null;
  company_name: string | null;
  company_domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
};

export type QualityListResult = {
  project_id: number;
  count: number;
  filters: { min_score: number | null; passed: boolean | null; limit: number };
  data: QualityListRow[];
};

export type QualityRunResult = {
  scanned: number;
  checked: number;
  persisted: number;
  failed: number;
  passed_count: number;
  failed_count: number;
  only_status: string[];
  only_missing: boolean;
  dry_run: boolean;
  message_ids: number[];
  items: { message_id: number; check_id: number | null; score: number; passed: boolean }[];
};

export const qualityApi = {
  check: (messageId: number, body?: { dry_run?: boolean }) =>
    api
      .post<QualityCheckResponse>(`/outreach/${messageId}/quality-check`, body ?? {})
      .then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    message_ids?: number[];
    only_missing?: boolean;
    only_status?: OutreachStatus[];
    dry_run?: boolean;
    limit?: number;
  }) => api.post<QualityRunResult>("/quality/run", opts).then((r) => r.data),
  getForMessage: (messageId: number, limit = 20) =>
    api
      .get<QualityMessageHistory>(`/outreach/${messageId}/quality`, { params: { limit } })
      .then((r) => r.data),
  list: (opts: {
    project_id: number;
    min_score?: number;
    passed?: boolean;
    limit?: number;
  }) =>
    api
      .get<QualityListResult>("/quality", {
        params: {
          project_id: opts.project_id,
          min_score: opts.min_score,
          passed: opts.passed,
          limit: opts.limit,
        },
      })
      .then((r) => r.data),
};

// ============================================================================
// File 15 — Sends
// ============================================================================
export const SEND_STATUSES = [
  "queued", "sending", "sent", "bounced", "failed", "opened", "replied",
] as const;
export type SendStatus = typeof SEND_STATUSES[number];

export type Send = {
  id: number;
  outreach_message_id: number;
  provider: string;
  message_id_external: string | null;
  status: SendStatus;
  attempted_at: string;
  sent_at: string | null;
  error_message: string | null;
  raw_response: Record<string, unknown> | null;
};

export type SendResponse = {
  message_id: number;
  ok: boolean;
  send_id?: number;
  provider?: string;
  message_id_external?: string | null;
  status?: SendStatus;
  attempted_at?: string;
  sent_at?: string | null;
  to?: string;
  error?: string;
  dry_run?: boolean;
};

export type SendListRow = Send & {
  subject: string | null;
  message_status: string | null;
  lead_id: number;
  priority_tier: string | null;
  final_score: number | null;
  company_name: string | null;
  company_domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
};

export type SendListResult = {
  project_id: number;
  count: number;
  filters: { status: SendStatus | null; limit: number };
  data: SendListRow[];
};

export type SendMessageHistory = {
  message_id: number;
  count: number;
  latest: Send | null;
  history: Send[];
};

export type SendBatchItem = {
  message_id: number;
  ok?: boolean;
  status?: SendStatus;
  error?: string;
  send_id?: number;
};

export type SendRunResult = {
  scanned: number;
  attempted: number;
  sent: number;
  failed: number;
  skipped_quota: number;
  skipped_status: number;
  max_per_day: number;
  sent_today: number;
  remaining: number;
  dry_run: boolean;
  items: SendBatchItem[];
};

export type SendQuota = {
  project_id: number;
  sent_today: number;
  max_per_day: number;
  remaining: number;
};

export const sendsApi = {
  send: (messageId: number, body?: { dry_run?: boolean; max_per_day?: number }) =>
    api
      .post<SendResponse>(`/outreach/${messageId}/send`, body ?? {})
      .then((r) => r.data),
  runBatch: (opts: {
    project_id?: number;
    message_ids?: number[];
    max_per_day?: number;
    dry_run?: boolean;
    limit?: number;
  }) => api.post<SendRunResult>("/sends/run", opts).then((r) => r.data),
  getForMessage: (messageId: number, limit = 20) =>
    api
      .get<SendMessageHistory>(`/outreach/${messageId}/sends`, { params: { limit } })
      .then((r) => r.data),
  list: (opts: { project_id: number; status?: SendStatus; limit?: number }) =>
    api
      .get<SendListResult>("/sends", {
        params: { project_id: opts.project_id, status: opts.status, limit: opts.limit },
      })
      .then((r) => r.data),
  quota: (project_id: number, max_per_day = 50) =>
    api
      .get<SendQuota>("/sends/quota", { params: { project_id, max_per_day } })
      .then((r) => r.data),
};

// ============================================================================
// File 16 — Replies
// ============================================================================
export const REPLY_INTENTS = [
  "positive", "negative", "oof", "unsubscribe", "info_request", "neutral",
] as const;
export type ReplyIntent = typeof REPLY_INTENTS[number];

export type Reply = {
  id: number;
  outreach_message_id: number;
  outreach_send_id: number | null;
  provider: string | null;
  message_id_external: string | null;
  in_reply_to: string | null;
  from_email: string | null;
  from_name: string | null;
  subject: string | null;
  body: string | null;
  body_html: string | null;
  intent: ReplyIntent | null;
  confidence: number | null;
  classifier: string | null;
  raw_response: Record<string, unknown> | null;
  received_at: string | null;
  created_at: string | null;
};

export type ReplyIngestResponse = {
  ok: boolean;
  reply_id?: number;
  outreach_message_id?: number;
  outreach_send_id?: number | null;
  intent?: ReplyIntent;
  confidence?: number;
  classifier?: string;
  suppressed?: boolean;
  from_email?: string | null;
  error?: string;
  dry_run?: boolean;
};

export type ReplyMessageHistory = {
  message_id: number;
  count: number;
  latest: Reply | null;
  history: Reply[];
};

export type ReplyListRow = Reply & {
  message_subject: string | null;
  message_status: string | null;
  lead_id: number;
  priority_tier: string | null;
  final_score: number | null;
  company_name: string | null;
  company_domain: string | null;
  contact_name: string | null;
  contact_email: string | null;
};

export type ReplyListResult = {
  project_id: number;
  count: number;
  filters: { intent: ReplyIntent | null; limit: number };
  data: ReplyListRow[];
};

export type ReplyPollResult = {
  scanned: number;
  ingested: number;
  suppressed: number;
  by_intent: Record<ReplyIntent, number>;
  dry_run: boolean;
  project_id: number | null;
  items: ReplyIngestResponse[];
};

export type ReplyDetail = {
  reply: Reply;
  message: Record<string, unknown> | null;
  send: Record<string, unknown> | null;
  lead: Record<string, unknown> | null;
};

export const repliesApi = {
  ingest: (payload: Record<string, unknown>) =>
    api.post<ReplyIngestResponse>("/replies/ingest", payload).then((r) => r.data),
  poll: (opts: { project_id?: number; dry_run?: boolean; limit?: number }) =>
    api.post<ReplyPollResult>("/replies/poll", opts).then((r) => r.data),
  getForMessage: (messageId: number, limit = 50) =>
    api
      .get<ReplyMessageHistory>(`/outreach/${messageId}/replies`, { params: { limit } })
      .then((r) => r.data),
  list: (opts: { project_id: number; intent?: ReplyIntent; limit?: number }) =>
    api
      .get<ReplyListResult>("/replies", {
        params: { project_id: opts.project_id, intent: opts.intent, limit: opts.limit },
      })
      .then((r) => r.data),
  get: (id: number) => api.get<ReplyDetail>(`/replies/${id}`).then((r) => r.data),
};

// ============================================================================
// File 17 — Engagement metrics + Campaign dashboard
// ============================================================================
export type DailySeriesPoint = {
  date: string;
  sent: number;
  opened: number;
  replied: number;
  bounced: number;
};

export type TopRepliedCompany = {
  company_id: number;
  company_name: string | null;
  replies: number;
};

export type FunnelStep = {
  discovered: number;
  scored: number;
  approved: number;
  sent: number;
  opened: number;
  replied: number;
  positive: number;
};

export type CampaignMetrics = {
  project_id: number;
  icp_id: number | null;
  window_days: number;
  computed_at: string | null;
  sent_count: number;
  sent_today: number;
  sent_7d: number;
  sent_30d: number;
  sent_window: number;
  opened_count: number;
  opened_rate: number;
  replied_count: number;
  reply_rate: number;
  positive_reply_count: number;
  positive_reply_rate: number;
  bounced_count: number;
  bounce_rate: number;
  failed_count: number;
  unsubscribed_count: number;
  unsubscribe_rate: number;
  by_status: Record<string, number>;
  by_intent: Record<string, number>;
  daily_series: DailySeriesPoint[];
  top_replied_companies: TopRepliedCompany[];
  funnel: FunnelStep;
  from_cache: boolean;
};

export type MetricsSeriesResponse = {
  project_id: number;
  icp_id: number | null;
  window_days: number;
  series: DailySeriesPoint[];
};

export type MetricsFunnelResponse = {
  project_id: number;
  icp_id: number | null;
  funnel: FunnelStep;
};

export type MetricsRecomputeResponse = {
  ok: boolean;
  project_id: number;
  icp_id: number | null;
  window_days: number;
  computed_at: string | null;
  metrics: CampaignMetrics;
};

export const metricsApi = {
  campaign: (opts: {
    project_id: number;
    icp_id?: number | null;
    window_days?: number;
    recompute?: boolean;
  }) =>
    api
      .get<CampaignMetrics>("/metrics/campaign", {
        params: {
          project_id: opts.project_id,
          icp_id: opts.icp_id ?? undefined,
          window_days: opts.window_days ?? 30,
          recompute: opts.recompute ?? false,
        },
      })
      .then((r) => r.data),
  series: (opts: { project_id: number; icp_id?: number | null; window_days?: number }) =>
    api
      .get<MetricsSeriesResponse>("/metrics/series", {
        params: {
          project_id: opts.project_id,
          icp_id: opts.icp_id ?? undefined,
          window_days: opts.window_days ?? 30,
        },
      })
      .then((r) => r.data),
  funnel: (opts: { project_id: number; icp_id?: number | null }) =>
    api
      .get<MetricsFunnelResponse>("/metrics/funnel", {
        params: {
          project_id: opts.project_id,
          icp_id: opts.icp_id ?? undefined,
        },
      })
      .then((r) => r.data),
  recompute: (opts: { project_id: number; icp_id?: number | null; window_days?: number }) =>
    api.post<MetricsRecomputeResponse>("/metrics/recompute", opts).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// File 18 — Outreach experiments (A/B variant testing)
// ---------------------------------------------------------------------------

export type Variant = {
  id: number;
  experiment_id: number;
  name: string;
  weight: number;
  subject_template: string | null;
  body_template: string | null;
  cta_template: string | null;
  params: Record<string, unknown>;
  is_control: boolean | number;
  created_at?: string;
};

export type Experiment = {
  id: number;
  project_id: number;
  icp_id: number | null;
  name: string;
  hypothesis: string | null;
  status: "draft" | "running" | "paused" | "completed" | "archived";
  allocation: "hash" | "random";
  primary_metric: string;
  min_sample_size: number;
  confidence_level: number;
  started_at: string | null;
  completed_at: string | null;
  winner_variant_id: number | null;
  config: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  variants?: Variant[];
  variant_count?: number;
};

export type LeadVariantAssignment = {
  id: number;
  lead_id: number;
  experiment_id: number;
  variant_id: number;
  assigned_at: string;
};

export type VariantStat = {
  variant_id: number;
  name: string;
  is_control: boolean;
  sent: number;
  replied: number;
  positive: number;
  reply_rate: number;
  positive_reply_rate: number;
  lift_vs_control: number | null;
  wilson_lower: number;
};

export type ExperimentScore = {
  experiment_id: number;
  status: string;
  primary_metric: string;
  min_sample_size: number;
  confidence_level: number;
  control_variant_id: number | null;
  by_variant: VariantStat[];
  leader_variant_id: number | null;
  winner_variant_id: number | null;
  ready_to_declare: boolean;
  computed_at: string;
};

export type ExperimentDetail = {
  experiment: Experiment;
  variants: Variant[];
  assignments_count: number;
  score: ExperimentScore | { error: string };
};

export type ExperimentVariantInput = {
  name: string;
  weight?: number;
  subject_template?: string | null;
  body_template?: string | null;
  cta_template?: string | null;
  is_control?: boolean;
};

export type CreateExperimentInput = {
  project_id: number;
  icp_id?: number | null;
  name: string;
  hypothesis?: string;
  allocation?: "hash" | "random";
  primary_metric?: string;
  min_sample_size?: number;
  confidence_level?: number;
  variants: ExperimentVariantInput[];
  config?: Record<string, unknown>;
};

export const experimentsApi = {
  list: (project_id: number, status?: string) =>
    api
      .get<{ count: number; data: Experiment[] }>("/experiments", {
        params: { project_id, status },
      })
      .then((r) => r.data),
  create: (input: CreateExperimentInput) =>
    api.post<Experiment>("/experiments", input).then((r) => r.data),
  get: (id: number) =>
    api.get<ExperimentDetail>(`/experiments/${id}`).then((r) => r.data),
  start: (id: number) =>
    api.post<Experiment>(`/experiments/${id}/start`).then((r) => r.data),
  pause: (id: number) =>
    api.post<Experiment>(`/experiments/${id}/pause`).then((r) => r.data),
  score: (id: number) =>
    api.post<ExperimentScore>(`/experiments/${id}/score`).then((r) => r.data),
  declare: (id: number, variant_id: number) =>
    api
      .post<Experiment>(`/experiments/${id}/declare`, { variant_id })
      .then((r) => r.data),
};

// ----- File 19: Lead Exports -----

export const EXPORT_DESTINATIONS = ["filesystem", "hubspot", "salesforce"] as const;
export type ExportDestination = (typeof EXPORT_DESTINATIONS)[number];

export const EXPORT_FORMATS = ["csv", "json"] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];

export const EXPORT_STATUSES = [
  "pending",
  "building",
  "ready",
  "delivered",
  "failed",
] as const;
export type ExportStatus = (typeof EXPORT_STATUSES)[number];

export type LeadExport = {
  id: number;
  project_id: number;
  icp_id: number | null;
  name: string;
  destination: ExportDestination;
  status: ExportStatus;
  format: ExportFormat;
  filters: Record<string, unknown> | null;
  artifact_path: string | null;
  artifact_size_bytes: number | null;
  row_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  delivered_at: string | null;
};

export type LeadExportItem = {
  id: number;
  lead_export_id: number;
  lead_id: number;
  outreach_message_id: number | null;
  variant_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ExportSummary = {
  row_count: number;
  artifact_size_bytes: number | null;
  destination: ExportDestination;
  status: ExportStatus;
  artifact_path: string | null;
  error_message: string | null;
};

export type CreateExportInput = {
  project_id: number;
  icp_id?: number | null;
  name: string;
  destination?: ExportDestination;
  format?: ExportFormat;
  filters?: Record<string, unknown> | null;
  dry_run?: boolean;
};

export type RunExportResult = {
  export: LeadExport;
  row_count: number;
  artifact_path?: string | null;
  artifact_size_bytes?: number | null;
  delivery: Record<string, unknown>;
};

export const exportsApi = {
  list: (project_id: number, status?: ExportStatus) =>
    api
      .get<{ count: number; data: LeadExport[] }>("/exports", {
        params: { project_id, status },
      })
      .then((r) => r.data),
  create: (input: CreateExportInput) =>
    api.post<RunExportResult>("/exports", input).then((r) => r.data),
  get: (id: number) =>
    api
      .get<{ export: LeadExport; item_count: number; summary: ExportSummary }>(
        `/exports/${id}`,
      )
      .then((r) => r.data),
  items: (id: number, limit = 500) =>
    api
      .get<{ count: number; data: LeadExportItem[] }>(`/exports/${id}/items`, {
        params: { limit },
      })
      .then((r) => r.data),
  downloadUrl: (id: number) => `${api.defaults.baseURL ?? ""}/exports/${id}/download`,
  redeliver: (id: number) =>
    api
      .post<{ export: LeadExport; delivery: Record<string, unknown> }>(
        `/exports/${id}/redeliver`,
      )
      .then((r) => r.data),
};

// ===========================================================================
// File 20 — Feedback ingestion + lifecycle
// ===========================================================================
export const FEEDBACK_KINDS = [
  "thumbs_up", "thumbs_down",
  "lead_qualified", "lead_disqualified",
  "meeting_booked", "won", "lost",
  "unsubscribe", "note",
] as const;
export type FeedbackKind = (typeof FEEDBACK_KINDS)[number];

export const FEEDBACK_SOURCES = [
  "human", "reply", "crm_sync", "export_delivered", "system",
] as const;
export type FeedbackSource = (typeof FEEDBACK_SOURCES)[number];

export const LIFECYCLE_STAGES = [
  "new", "contacted", "engaged", "qualified", "meeting_booked",
  "won", "lost", "unsubscribed", "disqualified",
] as const;
export type LifecycleStage = (typeof LIFECYCLE_STAGES)[number];

export type FeedbackEvent = {
  id: number;
  project_id: number;
  icp_id?: number | null;
  lead_id?: number | null;
  outreach_message_id?: number | null;
  variant_id?: number | null;
  source: FeedbackSource;
  kind: FeedbackKind;
  payload?: Record<string, unknown> | null;
  weight?: number | null;
  applied: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type LifecycleTransition = {
  id: number;
  lead_id: number;
  from_status?: string | null;
  to_status: LifecycleStage;
  reason?: string | null;
  source?: string | null;
  feedback_event_id?: number | null;
  created_at?: string | null;
};

export type FeedbackSummary = {
  by_kind: Record<string, number>;
  by_stage: Record<string, number>;
  recent: FeedbackEvent[];
};

export type RecordFeedbackInput = {
  project_id: number;
  kind: FeedbackKind;
  source?: FeedbackSource;
  lead_id?: number | null;
  icp_id?: number | null;
  outreach_message_id?: number | null;
  variant_id?: number | null;
  payload?: Record<string, unknown>;
  weight?: number;
  auto_apply?: boolean;
};

export const feedbackApi = {
  list: (params: {
    project_id: number; kind?: FeedbackKind; source?: FeedbackSource;
    applied?: number; limit?: number;
  }) =>
    api
      .get<{ count: number; data: FeedbackEvent[] }>("/feedback", { params })
      .then((r) => r.data),
  create: (input: RecordFeedbackInput) =>
    api
      .post<{ event: FeedbackEvent; transition: LifecycleTransition | null }>(
        "/feedback", input,
      )
      .then((r) => r.data),
  get: (id: number) =>
    api.get<FeedbackEvent>(`/feedback/${id}`).then((r) => r.data),
  apply: (project_id: number, limit = 200) =>
    api
      .post<{
        applied: number; transitions: unknown[];
        errors: unknown[]; scanned: number;
      }>("/feedback/apply", { project_id, limit })
      .then((r) => r.data),
  summary: (project_id: number) =>
    api
      .get<FeedbackSummary>("/feedback/summary", { params: { project_id } })
      .then((r) => r.data),
};

export const lifecycleApi = {
  get: (lead_id: number) =>
    api
      .get<{
        lead: Record<string, unknown>;
        lifecycle_stage: LifecycleStage;
        transitions: LifecycleTransition[];
      }>(`/leads/${lead_id}/lifecycle`)
      .then((r) => r.data),
  transition: (
    lead_id: number,
    to_status: LifecycleStage,
    reason?: string,
  ) =>
    api
      .post<{
        transition: LifecycleTransition;
        from_status: string;
        to_status: LifecycleStage;
        lead_id: number;
        sync: Record<string, unknown>;
      }>(`/leads/${lead_id}/transition`, { to_status, reason })
      .then((r) => r.data),
};

// ===========================================================================
// File 21 — Scoring weight auto-tuning + revisions
// ===========================================================================
export const REVISION_SOURCES = ["manual", "auto_tune", "rollback"] as const;
export type RevisionSource = (typeof REVISION_SOURCES)[number];

export const REVISION_STATUSES = ["proposed", "active", "archived", "rejected"] as const;
export type RevisionStatus = (typeof REVISION_STATUSES)[number];

export type WeightMap = { fit: Record<string, number>; signal: Record<string, number> };

export type ScoringRevision = {
  id: number;
  icp_id: number;
  project_id: number;
  parent_revision_id?: number | null;
  source: RevisionSource;
  status: RevisionStatus;
  proposed_weights: WeightMap;
  baseline_weights?: WeightMap | null;
  contributing_event_ids?: number[] | null;
  stats?: Record<string, unknown> | null;
  notes?: string | null;
  created_by?: string | null;
  activated_at?: string | null;
  archived_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WeightDiffRow = {
  namespace: "fit" | "signal";
  key: string;
  baseline: number;
  proposed: number;
  delta: number;
};

export type RevisionSummary = {
  icp_id: number;
  active: ScoringRevision | null;
  active_weights: WeightMap;
  module_defaults: WeightMap;
  proposed: ScoringRevision[];
  history: ScoringRevision[];
};

export type ProposeRevisionInput = {
  project_id: number;
  notes?: string;
  created_by?: string;
};

export type TuningRunResult = {
  project_id: number;
  icp_ids: number[];
  proposed_count: number;
  promoted_count: number;
  skipped_count: number;
  proposed: Array<Record<string, unknown>>;
  promoted: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  auto_promote: boolean;
  confidence_threshold: number;
};

export const tuningApi = {
  getWeights: (icpId: number) =>
    api.get<RevisionSummary>(`/icps/${icpId}/scoring/weights`).then((r) => r.data),
  listRevisions: (icpId: number, params?: { limit?: number }) =>
    api
      .get<{ count: number; data: ScoringRevision[] }>(
        `/icps/${icpId}/scoring/revisions`,
        { params },
      )
      .then((r) => r.data),
  getRevision: (revId: number) =>
    api
      .get<{ revision: ScoringRevision; diff: WeightDiffRow[] }>(
        `/scoring/revisions/${revId}`,
      )
      .then((r) => r.data),
  propose: (icpId: number, body: ProposeRevisionInput) =>
    api
      .post<{
        revision: ScoringRevision; baseline: WeightMap; proposed: WeightMap;
        stats: Record<string, unknown>; contributing_event_ids: number[];
        diff: WeightDiffRow[];
      }>(`/icps/${icpId}/scoring/propose`, body)
      .then((r) => r.data),
  approve: (revId: number) =>
    api
      .post<{ revision: ScoringRevision; previous_active_id: number | null }>(
        `/scoring/revisions/${revId}/approve`,
      )
      .then((r) => r.data),
  reject: (revId: number, body?: { reason?: string }) =>
    api
      .post<{ revision: ScoringRevision }>(
        `/scoring/revisions/${revId}/reject`, body ?? {},
      )
      .then((r) => r.data),
  rollback: (revId: number, body?: { created_by?: string; notes?: string }) =>
    api
      .post<{
        revision: ScoringRevision;
        previous_active_id: number | null;
        source_revision_id: number;
      }>(`/scoring/revisions/${revId}/rollback`, body ?? {})
      .then((r) => r.data),
  run: (body: {
    project_id: number; icp_ids?: number[];
    auto_promote?: boolean; confidence_threshold?: number;
    notes?: string; created_by?: string;
  }) => api.post<TuningRunResult>("/scoring/tuning/run", body).then((r) => r.data),
};

// ============================================================
// Pipeline Orchestration (File 22)
// ============================================================
export type TemplateStep = {
  run_type: string;
  config: Record<string, unknown>;
  on_failure: "stop" | "skip" | "continue";
};
export type PipelineTemplate = {
  id: number;
  project_id: number | null;
  name: string;
  slug: string;
  version: number;
  status: "draft" | "active" | "archived";
  steps: TemplateStep[];
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};
export type PipelineSchedule = {
  id: number;
  project_id: number;
  template_id: number;
  icp_id: number | null;
  name: string;
  cron_expr: string;
  timezone: string;
  enabled: number;
  last_fired_at: string | null;
  next_fire_at: string | null;
  last_run_id: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};
export type StageHealth = {
  run_type: string;
  count_total: number;
  count_success: number;
  count_failed: number;
  success_rate: number;
  p50_ms: number;
  p95_ms: number;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
};
export type StagesOverview = {
  project_id: number | null;
  limit: number;
  stages: StageHealth[];
};
export type RunTraceStep = {
  step_index: number;
  run_type: string;
  on_failure: string;
  run_id: number | null;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  total_processed: number;
  total_created: number;
  total_failed: number;
  error_message: string | null;
};
export type RunTrace = {
  run: Record<string, unknown> & { id: number; status: string };
  steps: Array<Record<string, unknown>>;
  summary: {
    template_id?: number;
    template_slug?: string;
    template_version?: number;
    step_count?: number;
    executed_count?: number;
    steps?: RunTraceStep[];
  };
  children: Array<{ step: RunTraceStep; child_run: Record<string, unknown> | null }>;
};
export type SchedulerTickResult = {
  now: string;
  due_count: number;
  fired_count: number;
  skipped_count: number;
  fired: Array<{ schedule_id: number; run_id: number; fired_at: string; next_fire_at: string }>;
  skipped: Array<{ schedule_id: number; reason: string }>;
};

export const templatesApi = {
  list: (params: { project_id?: number; include_global?: boolean; status?: string; limit?: number }) =>
    api.get<PipelineTemplate[]>("/pipeline/templates", { params }).then((r) => r.data),
  get: (id: number) =>
    api.get<PipelineTemplate>(`/pipeline/templates/${id}`).then((r) => r.data),
  create: (body: {
    project_id?: number | null; name: string; slug: string;
    steps: TemplateStep[]; notes?: string; created_by?: string; status?: string;
  }) => api.post<PipelineTemplate>("/pipeline/templates", body).then((r) => r.data),
  update: (id: number, body: Partial<{
    name: string; status: string; steps: TemplateStep[]; notes: string;
  }>) => api.patch<PipelineTemplate>(`/pipeline/templates/${id}`, body).then((r) => r.data),
  clone: (id: number, body: { name?: string; project_id?: number; created_by?: string }) =>
    api.post<PipelineTemplate>(`/pipeline/templates/${id}/clone`, body).then((r) => r.data),
  archive: (id: number) =>
    api.delete<PipelineTemplate>(`/pipeline/templates/${id}`).then((r) => r.data),
  run: (body: {
    template_id?: number; template_slug?: string; project_id: number;
    icp_id?: number; overrides?: Record<string, Record<string, unknown>>; dry_run?: boolean;
  }) =>
    api.post<{ parent_run_id: number; template_id: number }>(
      "/pipeline/templates/run", body,
    ).then((r) => r.data),
};

export const schedulesApi = {
  list: (project_id: number, limit?: number) =>
    api.get<PipelineSchedule[]>("/pipeline/schedules", {
      params: { project_id, limit },
    }).then((r) => r.data),
  get: (id: number) =>
    api.get<PipelineSchedule>(`/pipeline/schedules/${id}`).then((r) => r.data),
  create: (body: {
    project_id: number; template_id: number; icp_id?: number;
    name: string; cron_expr: string; timezone?: string; enabled?: boolean; notes?: string;
  }) => api.post<PipelineSchedule>("/pipeline/schedules", body).then((r) => r.data),
  update: (id: number, body: Partial<{
    name: string; template_id: number; icp_id: number | null;
    cron_expr: string; timezone: string; enabled: boolean; notes: string;
  }>) => api.patch<PipelineSchedule>(`/pipeline/schedules/${id}`, body).then((r) => r.data),
  remove: (id: number) =>
    api.delete<{ ok: boolean; schedule_id: number }>(`/pipeline/schedules/${id}`).then((r) => r.data),
  fireNow: (id: number) =>
    api.post<{ schedule_id: number; run_id: number; fired_at: string; next_fire_at: string }>(
      `/pipeline/schedules/${id}/fire-now`, {},
    ).then((r) => r.data),
};

export const schedulerApi = {
  tick: (limit = 50) =>
    api.post<SchedulerTickResult>("/pipeline/scheduler/tick", { limit }).then((r) => r.data),
};

export const pipelineHealthApi = {
  overview: (params: { project_id?: number; limit?: number }) =>
    api.get<StagesOverview>("/pipeline/health", { params }).then((r) => r.data),
  forStage: (run_type: string, params: { project_id?: number; limit?: number }) =>
    api.get<StageHealth>(`/pipeline/health/${run_type}`, { params }).then((r) => r.data),
};

export const runTraceApi = {
  get: (run_id: number) =>
    api.get<RunTrace>(`/pipeline/runs/${run_id}/trace`).then((r) => r.data),
};

// ── File 23 — Conversation Layer ─────────────────────────────────────────────

export type LeadThread = {
  id: number;
  project_id: number;
  icp_id: number | null;
  lead_id: number | null;
  contact_id: number | null;
  subject: string | null;
  status: "open" | "awaiting_reply" | "replied" | "closed" | "bounced";
  last_message_at: string | null;
  last_direction: "out" | "in" | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type ThreadMessage = {
  id: number;
  thread_id: number;
  direction: "out" | "in";
  source: "outreach_send" | "outreach_reply" | "manual" | "reply_draft";
  external_id: string | null;
  send_id: number | null;
  reply_id: number | null;
  draft_id: number | null;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  sent_at: string | null;
  received_at: string | null;
  decision_trace_id: number | null;
  decision_trace: DecisionTrace | null;
  created_at: string;
};

export type LeadThreadDetail = LeadThread & { messages: ThreadMessage[] };

export type DecisionTrace = {
  id: number;
  pipeline_run_id: number | null;
  step_index: number | null;
  module_name: string;
  lead_id: number | null;
  contact_id: number | null;
  decision_type: "score" | "draft" | "quality" | "send" | "reply" | "tuning" | "thread";
  input_snapshot: Record<string, unknown> | null;
  rationale: string | null;
  model_name: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  confidence: number | null;
  created_at: string;
};

export const threadsApi = {
  list: (params: { project_id: number; status?: string; limit?: number }) =>
    api.get<{ count: number; data: LeadThread[] }>("/threads", { params }).then((r) => r.data),
  create: (body: {
    project_id: number;
    icp_id?: number;
    lead_id?: number;
    contact_id?: number;
    subject?: string;
    status?: string;
  }) => api.post<LeadThread>("/threads", body).then((r) => r.data),
  get: (id: number) =>
    api.get<LeadThreadDetail>(`/threads/${id}`).then((r) => r.data),
  patch: (id: number, body: { status?: string }) =>
    api.patch<LeadThread>(`/threads/${id}`, body).then((r) => r.data),
  addMessage: (id: number, body: { direction: "out" | "in"; subject?: string; body_text?: string }) =>
    api.post<ThreadMessage>(`/threads/${id}/messages`, body).then((r) => r.data),
  draftReply: (id: number) =>
    api.post<{ run_id: number; latest_message: ThreadMessage }>(`/threads/${id}/draft-reply`, {}).then((r) => r.data),
  reconcile: (project_id: number) =>
    api.post<{ created: number; updated: number; skipped: number }>("/threads/reconcile", null, { params: { project_id } }).then((r) => r.data),
};

export const decisionTracesApi = {
  list: (params: { run_id?: number; lead_id?: number; contact_id?: number; decision_type?: string; limit?: number }) =>
    api.get<{ count: number; data: DecisionTrace[] }>("/decision-traces", { params }).then((r) => r.data),
  get: (id: number) =>
    api.get<DecisionTrace>(`/decision-traces/${id}`).then((r) => r.data),
};
