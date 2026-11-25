export type PlatformType = 'linkedin' | 'x' | 'instagram';
export type DepthType = 'concise' | 'standard' | 'deep';
export type WorkflowStrategyType =
  | 'multi_agent'
  | 'single_agent'
  | 'no_editor'
  | 'no_fact_checker';

export type RunStatusType =
  | 'queued'
  | 'running'
  | 'waiting_for_input'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled';

export type SourceStatusType =
  | 'retrieved'
  | 'partially_retrieved'
  | 'inaccessible'
  | 'unsupported_content_type'
  | 'failed';

export type ClaimStatusType =
  | 'supported'
  | 'partially_supported'
  | 'contradicted'
  | 'unsupported'
  | 'uncertain'
  | 'not_checked';

export interface ProjectDefaults {
  platform: PlatformType;
  audience: string | null;
  tone: string | null;
  depth: DepthType;
  language: string;
  required_points: string[];
  prohibited_points: string[];
}

export interface ProjectRead {
  project_id: string;
  name: string;
  description: string | null;
  defaults: ProjectDefaults;
  run_count: number;
  last_activity_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  items: ProjectRead[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContentRequestPayload {
  topic: string;
  goal: string;
  platform: PlatformType;
  audience: string | null;
  tone: string | null;
  depth: DepthType;
  language: string;
  call_to_action: string | null;
  constraints: string[];
  required_points: string[];
  prohibited_points: string[];
  source_urls: string[];
  source_notes: string | null;
  source_preference: string[];
  length_hint: string | null;
  project_id: string | null;
  workflow_strategy: WorkflowStrategyType;
  use_demo_mode: boolean;
  advanced: {
    model_override: string | null;
    temperature: number;
    search_depth: 'basic' | 'advanced';
    time_scope: 'day' | 'week' | 'month' | 'year' | null;
    editor_threshold: number | null;
  };
}

export interface SourceRecord {
  source_id: string;
  url: string;
  canonical_url: string;
  title: string;
  publisher: string;
  published_at: string | null;
  accessed_at: string;
  snippet: string;
  fetched_text_excerpt: string | null;
  credibility_score: number | null;
  relevance_score: number | null;
  source_type: string;
  status: SourceStatusType;
  fetch_error: string | null;
}

export interface EvidenceItem {
  evidence_id: string;
  source_id: string;
  source_url: string | null;
  source_title: string | null;
  quote_or_paraphrase: string;
  location_hint: string | null;
  related_claim_ids: string[];
  support_type: string;
  confidence: number | null;
  created_by_node: string;
}

export interface ClaimRecord {
  claim_id: string;
  claim_text: string;
  claim_type: string;
  materiality: 'high' | 'medium' | 'low';
  status: ClaimStatusType;
  confidence: number | null;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  explanation: string;
  recommended_action: 'keep' | 'qualify' | 'correct' | 'remove';
}

export interface ArtifactSummary {
  artifact_id: string;
  version: number;
  parent_version_id: string | null;
  title: string;
  platform: PlatformType;
  word_count: number;
  char_count: number;
  created_at: string;
  created_by: string;
  status: 'draft' | 'approved' | 'partial' | 'user_edited';
  differs_from_agent_approved: boolean;
}

export interface DraftArtifact extends ArtifactSummary {
  run_id: string;
  hook: string | null;
  body_markdown: string;
  outline: string[];
  thread_segments: string[];
  claims: ClaimRecord[];
  sources: SourceRecord[];
  evidence_items: EvidenceItem[];
}

export interface NodeMetric {
  metric_id: string;
  node_name: string;
  attempt: number;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  model_latency_ms: number | null;
  tool_latency_ms: number | null;
  provider: string | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  estimated_cost: number | null;
  cost_status: string;
  rate_card_version: string | null;
  currency: string | null;
  tool_calls: number;
  prompt_version: string | null;
  status: string;
  error_code: string | null;
}

export interface RunEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  node: string | null;
  event_type: string;
  status: string;
  message: string;
  safe_payload: Record<string, unknown>;
  created_at: string;
}

export interface RunQualitySummary {
  editor_score: number | null;
  editor_verdict: 'approve' | 'revise' | 'blocked' | null;
  fact_status: 'pass' | 'pass_with_warnings' | 'needs_revision' | 'blocked' | null;
  total_material_claims: number;
  supported_claims: number;
  partially_supported_claims: number;
  unsupported_claims: number;
  contradicted_claims: number;
  uncertain_claims: number;
  evidence_coverage: number | null;
  warning_count: number;
}

export interface RunMetricsSummary {
  duration_ms: number | null;
  total_input_tokens: number | null;
  total_output_tokens: number | null;
  total_tokens: number | null;
  token_usage_status: string;
  estimated_cost: number | null;
  cost_status: string;
  rate_card_version: string | null;
  currency: string | null;
  editor_revision_count: number;
  fact_remediation_count: number;
  research_retry_count: number;
  total_step_count: number;
}

export interface RunWarning {
  code: string;
  message: string;
  node: string | null;
}

export interface RunSummary {
  run_id: string;
  project_id: string | null;
  parent_run_id: string | null;
  status: RunStatusType;
  execution_mode: string;
  workflow_strategy: WorkflowStrategyType;
  topic: string;
  platform: PlatformType;
  current_node: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  editor_score: number | null;
  fact_status: string | null;
  evidence_coverage: number | null;
  total_tokens: number | null;
  estimated_cost: number | null;
  cost_status: string;
  warning_count: number;
  terminal_reason: string | null;
}

export interface RunDetail {
  run_id: string;
  project_id: string | null;
  parent_run_id: string | null;
  status: RunStatusType;
  execution_mode: string;
  workflow_strategy: WorkflowStrategyType;
  platform: PlatformType;
  current_node: string | null;
  request: Record<string, unknown>;
  normalized_brief: Record<string, unknown> | null;
  research_brief: {
    research_summary?: string;
    research_questions?: string[];
    key_findings?: { finding: string; evidence_ids: string[] }[];
    open_questions?: string[];
    confidence_notes?: string[];
  } | null;
  editor_result: {
    score: number;
    score_breakdown: Record<string, number>;
    verdict: string;
    critical_issues: string[];
    major_issues: string[];
    minor_issues: string[];
    rewrite_instructions: string[];
    summary: string;
  } | null;
  fact_check_result: {
    overall_status: string;
    evidence_coverage: number | null;
    unsupported_count: number;
    contradicted_count: number;
    uncertain_count: number;
    critical_findings: string[];
    rewrite_instructions: string[];
    limitations: string[];
  } | null;
  warnings: RunWarning[];
  errors: { code?: string; message?: string; node?: string }[];
  prompt_versions: Record<string, string>;
  quality: RunQualitySummary;
  metrics: RunMetricsSummary;
  node_metrics: NodeMetric[];
  sources: SourceRecord[];
  evidence_items: EvidenceItem[];
  claims: ClaimRecord[];
  artifacts: ArtifactSummary[];
  latest_artifact: DraftArtifact | null;
  events: RunEvent[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  terminal_reason: string | null;
}

export interface RunListResponse {
  items: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface BenchmarkTopic {
  topic_id: string;
  category: string;
  risk_profile: string;
  topic: string;
  goal: string;
  platform: PlatformType;
  audience: string;
  depth: DepthType;
  expected_risk_notes: string;
  is_holdout: boolean;
}

export interface BenchmarkCase {
  case_id: string;
  topic_id: string;
  topic: string;
  category: string;
  risk_profile: string;
  condition: WorkflowStrategyType;
  repeat_index: number;
  run_id: string | null;
  status: string;
  editor_score: number | null;
  evidence_coverage: number | null;
  unsupported_claim_rate: number | null;
  contradiction_rate: number | null;
  duration_ms: number | null;
  total_tokens: number | null;
  estimated_cost: number | null;
  cost_status: string;
  revision_count: number;
  human_rating: number | null;
  human_notes: string | null;
}

export interface BenchmarkConditionSummary {
  condition: WorkflowStrategyType;
  sample_size: number;
  completed_count: number;
  failed_count: number;
  error_rate: number;
  avg_editor_score: number | null;
  median_editor_score: number | null;
  avg_evidence_coverage: number | null;
  avg_unsupported_rate: number | null;
  avg_contradiction_rate: number | null;
  median_duration_ms: number | null;
  p90_duration_ms: number | null;
  total_tokens: number | null;
  total_estimated_cost: number | null;
  cost_per_accepted_artifact: number | null;
  cost_status: string;
  avg_human_rating: number | null;
  human_rating_count: number;
}

export interface BenchmarkDetail {
  benchmark_id: string;
  name: string;
  dataset_version: string;
  status: string;
  execution_mode: string;
  config: Record<string, unknown>;
  condition_summaries: BenchmarkConditionSummary[];
  cases: BenchmarkCase[];
  limitations: string[];
  created_at: string;
  finished_at: string | null;
}

export interface BenchmarkListResponse {
  items: BenchmarkDetail[];
  total: number;
  limit: number;
  offset: number;
}

export interface SupportedModelInfo {
  id: string;
  label: string;
  provider: string;
  tier: string;
  description: string;
  configured?: boolean;
  input_price_per_million?: number | null;
  output_price_per_million?: number | null;
}

export interface PublishArtifactResponse {
  platform: PlatformType;
  mode: 'direct_api' | 'composer_ready';
  published: boolean;
  post_url: string | null;
  composer_url: string | null;
  message: string;
}

export interface IntegrationsStatus {
  app_env: string;
  llm_provider: string;
  llm_model: string;
  available_models?: SupportedModelInfo[];
  llm_configured: boolean;
  llm_masked_label: string;
  configured_providers?: string[];
  provider_statuses?: Record<string, boolean>;
  social_connections?: Record<string, boolean>;
  search_provider: string;
  search_configured: boolean;
  search_masked_label: string;
  demo_mode_env: boolean;
  effective_default_mode: string;
  database_dialect: string;
  langsmith_enabled: boolean;
  rate_card_version: string;
  guardrails: Record<string, number>;
  privacy_note: string;
}

export interface DashboardSummary {
  total_runs: number;
  completed_runs: number;
  completed_with_warnings_runs: number;
  failed_runs: number;
  cancelled_runs: number;
  active_runs: number;
  avg_editor_score: number | null;
  editor_score_sample_size: number;
  avg_evidence_coverage: number | null;
  total_unsupported_claims: number;
  total_contradicted_claims: number;
  median_duration_ms: number | null;
  p90_duration_ms: number | null;
  total_tokens: number | null;
  total_estimated_cost: number | null;
  cost_status: string;
  avg_editor_revisions: number | null;
  avg_fact_remediations: number | null;
  provider_health: {
    rate_limit: number;
    timeout: number;
    other_failure: number;
  };
}
