import type { CodexAnalysis } from "@policylens/contracts";
export type Page =
  | "dashboard"
  | "search"
  | "policies"
  | "policy-detail"
  | "mainland"
  | "hong-kong"
  | "pet"
  | "other-lines"
  | "product-detail"
  | "comparison"
  | "import"
  | "retirement"
  | "sources"
  | "reminders"
  | "settings";

export interface ResearchDashboardData {
  insurers: Array<{ id: string; brand_name: string }>;
  research_runs: number;
  waiting_review: number;
  hk_products: number;
  active_hk_products: number;
  recent_runs: ResearchRunView[];
}

export interface ResearchReadinessView {
  ready: boolean;
  manual_confirmation_required: true;
  active_run_id: string | null;
  checks: Array<{ id: string; ready: boolean; message: string }>;
}

export interface ResearchPreviewView {
  scope: { jurisdiction: "HK"; categories: string[]; insurer_ids: string[]; max_products_per_insurer: number };
  insurers: Array<{ id: string; brand_name: string; legal_name: string; official_hosts: string[] }>;
  query_summary: string;
  will_send: string[];
  will_not_send: string[];
  usage_notice: string;
  argument_profile: string;
  requires_confirmation: true;
  preview_hash: string;
}

export interface ResearchLeadView {
  id: string;
  insurer_id: string;
  title: string;
  url: string;
  channel: "OFFICIAL_SEARCH" | "THIRD_PARTY_LEAD";
  authority: string;
  status: string;
  rejection_code: string | null;
  import_id: string | null;
}

export interface ResearchRunView {
  id: string;
  status: string;
  summary: {
    discovered_products?: number; waiting_review?: number; rejected_products?: number; lead_only?: number;
    execution?: {
      phase: string; elapsed_seconds: number; timeout_seconds: number;
      events_observed: number; web_searches: number; last_event_elapsed_seconds: number | null;
    };
  };
  error_code: string | null;
  cancel_requested: boolean;
  created_at: string;
  leads: ResearchLeadView[];
  insurer_outcomes: Array<{
    insurer_id: string;
    brand_name: string;
    status: string;
    official_candidates: number;
    official_leads?: number;
    waiting_review: number;
    published: number;
    rejected: number;
    lead_only: number;
    error_codes: string[];
  }>;
}

export interface ResearchCandidateView {
  import_id: string;
  run_id: string;
  review_status: string;
  verification_label: "UNVERIFIED_CANDIDATE" | "REVIEW_COMPLETED";
  display_name: string;
  version_label: string;
  insurer_id: string;
  jurisdiction: string | null;
  line_of_business: string | null;
  currency: string | null;
  sale_status: string | null;
  missing_fields: string[];
  field_count: number;
  published_product_version_id: string | null;
  source: ImportView["source"] & { canonical_url?: string | null; fetched_at?: string | null };
  fields: CandidateView[];
}

export interface CandidateComparisonView {
  candidates: Array<{
    import_id: string;
    display_name: string;
    version_label: string;
    insurer_id: string;
    review_status: string;
    verification_label: string;
  }>;
  rows: Array<{
    field_path: string;
    cells: Array<{
      import_id: string;
      candidate_id: string | null;
      value: string | null;
      unit: string | null;
      verification_status: string;
      guarantee_type: string;
      source_authority: string | null;
      page_number: number | null;
      excerpt: string | null;
      source_url: string | null;
    }>;
  }>;
  notice: string;
}

export interface EvidenceComparisonView {
  products: Array<{ version_id: string; display_name: string; version_label: string; insurer_id: string | null }>;
  rows: Array<{
    field_path: string;
    cells: Array<{ version_id: string; value: string | null; unit: string | null; verification_status: string; guarantee_type: string; evidence_count: number; evidence_ids: string[] }>;
  }>;
  notice: string;
}

export interface SearchResultView {
  query: string;
  products: ProductSummary[];
  candidates: ResearchCandidateView[];
  sources: SourceView[];
}

export interface CandidateView {
  id: string;
  field_path: string;
  value: string;
  raw_value: string;
  unit: string | null;
  page_number: number | null;
  excerpt: string;
  excerpt_hash: string;
  verification_status: string;
  value_origin: string;
  source_authority: string;
  guarantee_type: string;
  decision: string | null;
}

export interface ImportView {
  id: string;
  status: string;
  duplicate: boolean;
  source: {
    id: string;
    title: string;
    document_type: string;
    authority: string;
    page_count: number;
    sha256: string;
  };
  candidates: CandidateView[];
}

export interface ProductSummary {
  id: string;
  display_name: string;
  jurisdiction: string;
  line_of_business: string;
  currency: string;
  version_id: string;
  version_label: string;
  record_status: string;
  verified_facts: number;
  insurer_id: string | null;
  product_category: string | null;
  sale_status: string | null;
}

export interface EvidenceView {
  source_id: string;
  id: string;
  page_number: number | null;
  excerpt: string;
  excerpt_hash: string;
  authority: string;
}

export interface ProductDetail extends ProductSummary {
  facts: Array<{
    id: string;
    field_path: string;
    normalized_value: string;
    unit: string | null;
    guarantee_type: string;
    verification_status: string;
    value_origin: string;
    evidence: EvidenceView[];
  }>;
  renewal_terms: (Record<string, unknown> & {
    renewal_mode?: string;
    guarantee_period_years?: number | null;
    maximum_renewal_age?: number | null;
  }) | null;
  premium_rate: (Record<string, unknown> & { amount?: string; currency?: string }) | null;
  rate_adjustment_rule: (Record<string, unknown> & { scope?: string }) | null;
}

export interface PolicyView {
  id: string;
  member_nickname: string;
  category: string;
  status: string;
  product: ProductDetail;
  premium_records: Array<Record<string, string | null>>;
}

export interface SourceView {
  id: string;
  title: string;
  document_type: string;
  authority: string;
  page_count: number;
  sha256: string;
  status: string;
  evidence_count: number;
  imported_at: string;
  canonical_url: string | null;
  fetched_at: string | null;
  content_type: string | null;
}

export interface PreviewView {
  payload: Record<string, unknown> & {
    comparison: {
      evidenceExcerpts: Array<{ evidenceId: string; text: string; authority: string }>;
    };
  };
  preview_hash: string;
  excerpt_count: number;
  excerpt_characters: number;
  warnings: string[];
}

export interface PreviewSelectionView {
  requires_selection: true;
  evidence_options: Array<{
    evidenceId: string;
    text: string;
    authority: string;
    field: string;
    product: string;
  }>;
  limits: { max_excerpts: number; max_each_characters: number; max_total: number };
  message: string;
}

export interface AnalysisView {
  id: string;
  status: "DRAFT" | "ACCEPTED_AS_NOTE" | "REJECTED";
  result: CodexAnalysis;
  fact_verification_changed: false;
}

export interface RestorePreview {
  restore_token: string;
  source_count: number;
  product_count: number;
  policy_count: number;
  backup_created_at: string;
  current_data_unchanged: boolean;
}
