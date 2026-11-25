from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.security import UnsafeURLError, validate_url_syntax
from app.schemas.common import (
    ArtifactStatusType,
    ClaimMaterialityType,
    ClaimStatusType,
    DepthType,
    EditorVerdictType,
    EvidenceRoleType,
    FactOverallStatusType,
    PlatformType,
    RecommendedActionType,
    RunStatusType,
    SourceStatusType,
    WorkflowStrategyType,
)


class ProjectDefaults(BaseModel):
    platform: PlatformType = "linkedin"
    audience: str | None = Field(default=None, max_length=300)
    tone: str | None = Field(default=None, max_length=200)
    depth: DepthType = "standard"
    language: str = Field(default="en", max_length=20)
    required_points: list[str] = Field(default_factory=list, max_length=20)
    prohibited_points: list[str] = Field(default_factory=list, max_length=20)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    defaults: ProjectDefaults = Field(default_factory=ProjectDefaults)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("Project name must contain at least 2 useful characters.")
        return stripped


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    defaults: ProjectDefaults | None = None


class ProjectRead(BaseModel):
    project_id: str
    name: str
    description: str | None
    defaults: ProjectDefaults
    run_count: int = 0
    last_activity_at: str | None = None
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    items: list[ProjectRead]
    total: int
    limit: int
    offset: int


class AdvancedWorkflowOptions(BaseModel):
    model_override: str | None = Field(default=None, max_length=120)
    provider_override: str | None = Field(default=None, max_length=40)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    search_depth: str = Field(default="advanced", pattern="^(basic|advanced)$")
    time_scope: str | None = Field(default=None, pattern="^(day|week|month|year)$")
    editor_threshold: int | None = Field(default=None, ge=50, le=100)
    mock_scenario: str | None = Field(default=None, max_length=64)


class ContentRequest(BaseModel):
    topic: str = Field(min_length=5, max_length=12000)
    goal: str = Field(
        default="Inform and educate the target audience", min_length=2, max_length=500
    )
    platform: PlatformType = "linkedin"
    audience: str | None = Field(default=None, max_length=400)
    tone: str | None = Field(default=None, max_length=200)
    depth: DepthType = "standard"
    language: str = Field(default="en", min_length=2, max_length=20)
    call_to_action: str | None = Field(default=None, max_length=400)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    required_points: list[str] = Field(default_factory=list, max_length=20)
    prohibited_points: list[str] = Field(default_factory=list, max_length=20)
    source_urls: list[str] = Field(default_factory=list, max_length=16)
    source_notes: str | None = Field(default=None, max_length=6000)
    source_preference: list[str] = Field(default_factory=list, max_length=20)
    length_hint: str | None = Field(default=None, max_length=100)
    project_id: str | None = Field(default=None, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    workflow_strategy: WorkflowStrategyType = "multi_agent"
    use_demo_mode: bool = False
    advanced: AdvancedWorkflowOptions = Field(default_factory=AdvancedWorkflowOptions)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        settings = get_settings()
        cleaned = " ".join(v.strip().split())
        if len(cleaned) < 5:
            raise ValueError("Topic must contain at least 5 useful characters.")
        if len(cleaned) > settings.max_input_characters:
            raise ValueError(
                f"Topic exceeds maximum input limit ({settings.max_input_characters} characters)."
            )
        return v.strip()

    @field_validator("source_notes")
    @classmethod
    def validate_source_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        settings = get_settings()
        cleaned = v.strip()
        if not cleaned:
            return None
        if len(cleaned) > settings.max_input_characters:
            raise ValueError("Source notes exceed maximum input limit.")
        return cleaned

    @field_validator("source_urls")
    @classmethod
    def validate_source_urls(cls, urls: list[str]) -> list[str]:
        settings = get_settings()
        if len(urls) > settings.max_urls_per_request:
            raise ValueError(
                f"At most {settings.max_urls_per_request} source URLs may be supplied per run."
            )
        validated: list[str] = []
        seen: set[str] = set()
        for raw in urls:
            if not raw or not raw.strip():
                continue
            try:
                checked = validate_url_syntax(raw)
            except UnsafeURLError as exc:
                raise ValueError(str(exc)) from exc
            if checked not in seen:
                seen.add(checked)
                validated.append(checked)
        return validated


class NormalizedBrief(BaseModel):
    topic: str
    goal: str
    platform: PlatformType
    audience: str
    tone: str
    depth: DepthType
    language: str
    call_to_action: str | None = None
    constraints: list[str] = Field(default_factory=list)
    required_points: list[str] = Field(default_factory=list)
    prohibited_points: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_notes: str | None = None
    source_preference: list[str] = Field(default_factory=list)
    length_hint: str
    workflow_strategy: WorkflowStrategyType = "multi_agent"
    editor_threshold: int = 75


class SourceRecordRead(BaseModel):
    source_id: str
    url: str
    canonical_url: str
    title: str
    publisher: str
    published_at: str | None = None
    accessed_at: str
    snippet: str
    fetched_text_excerpt: str | None = None
    credibility_score: float | None = None
    relevance_score: float | None = None
    source_type: str
    status: SourceStatusType
    fetch_error: str | None = None


class EvidenceItemRead(BaseModel):
    evidence_id: str
    source_id: str
    source_url: str | None = None
    source_title: str | None = None
    quote_or_paraphrase: str
    location_hint: str | None = None
    related_claim_ids: list[str] = Field(default_factory=list)
    support_type: EvidenceRoleType
    confidence: float | None = None
    created_by_node: str


class ClaimRecordRead(BaseModel):
    claim_id: str
    claim_text: str
    claim_type: str
    materiality: ClaimMaterialityType
    status: ClaimStatusType
    confidence: float | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str
    recommended_action: RecommendedActionType


class DraftArtifactRead(BaseModel):
    artifact_id: str
    run_id: str
    version: int
    parent_version_id: str | None = None
    title: str
    hook: str | None = None
    body_markdown: str
    platform: PlatformType
    outline: list[str] = Field(default_factory=list)
    thread_segments: list[str] = Field(default_factory=list)
    word_count: int
    char_count: int
    created_at: str
    created_by: str
    status: ArtifactStatusType
    differs_from_agent_approved: bool = False
    claims: list[ClaimRecordRead] = Field(default_factory=list)
    sources: list[SourceRecordRead] = Field(default_factory=list)
    evidence_items: list[EvidenceItemRead] = Field(default_factory=list)


class ArtifactSummaryRead(BaseModel):
    artifact_id: str
    version: int
    parent_version_id: str | None = None
    title: str
    platform: PlatformType
    word_count: int
    char_count: int
    created_at: str
    created_by: str
    status: ArtifactStatusType
    differs_from_agent_approved: bool = False


class ArtifactEditRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body_markdown: str = Field(min_length=1, max_length=30000)
    expected_parent_version_id: str | None = None


class PublishArtifactRequest(BaseModel):
    platform: PlatformType
    text: str = Field(min_length=1, max_length=20000)


class PublishArtifactResponse(BaseModel):
    platform: PlatformType
    mode: Literal["direct_api", "composer_ready"]
    published: bool
    post_url: str | None = None
    composer_url: str | None = None
    message: str


class NodeMetricRead(BaseModel):
    metric_id: str
    node_name: str
    attempt: int
    started_at: str
    ended_at: str
    duration_ms: int
    model_latency_ms: int | None = None
    tool_latency_ms: int | None = None
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    cost_status: str = "unavailable"
    rate_card_version: str | None = None
    currency: str | None = None
    tool_calls: int = 0
    prompt_version: str | None = None
    status: str
    error_code: str | None = None


class RunEventRead(BaseModel):
    event_id: str
    run_id: str
    sequence: int
    node: str | None = None
    event_type: str
    status: str
    message: str
    safe_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class RunQualitySummary(BaseModel):
    editor_score: int | None = None
    editor_verdict: EditorVerdictType | None = None
    fact_status: FactOverallStatusType | None = None
    total_material_claims: int = 0
    supported_claims: int = 0
    partially_supported_claims: int = 0
    unsupported_claims: int = 0
    contradicted_claims: int = 0
    uncertain_claims: int = 0
    evidence_coverage: float | None = None
    warning_count: int = 0


class RunMetricsSummary(BaseModel):
    duration_ms: int | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_tokens: int | None = None
    token_usage_status: str = "unavailable"
    estimated_cost: float | None = None
    cost_status: str = "unavailable"
    rate_card_version: str | None = None
    currency: str | None = None
    editor_revision_count: int = 0
    fact_remediation_count: int = 0
    research_retry_count: int = 0
    total_step_count: int = 0


class RunWarning(BaseModel):
    code: str
    message: str
    node: str | None = None


class RunCreateResponse(BaseModel):
    run_id: str
    status: RunStatusType
    execution_mode: str
    events_url: str


class RunSummaryRead(BaseModel):
    run_id: str
    project_id: str | None = None
    parent_run_id: str | None = None
    status: RunStatusType
    execution_mode: str
    workflow_strategy: WorkflowStrategyType
    topic: str
    platform: PlatformType
    current_node: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    editor_score: int | None = None
    fact_status: FactOverallStatusType | None = None
    evidence_coverage: float | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    cost_status: str = "unavailable"
    warning_count: int = 0
    terminal_reason: str | None = None


class RunDetailRead(BaseModel):
    run_id: str
    project_id: str | None = None
    parent_run_id: str | None = None
    status: RunStatusType
    execution_mode: str
    workflow_strategy: WorkflowStrategyType
    platform: PlatformType
    current_node: str | None = None
    request: dict[str, Any]
    normalized_brief: NormalizedBrief | None = None
    research_brief: dict[str, Any] | None = None
    editor_result: dict[str, Any] | None = None
    fact_check_result: dict[str, Any] | None = None
    warnings: list[RunWarning] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    quality: RunQualitySummary
    metrics: RunMetricsSummary
    node_metrics: list[NodeMetricRead] = Field(default_factory=list)
    sources: list[SourceRecordRead] = Field(default_factory=list)
    evidence_items: list[EvidenceItemRead] = Field(default_factory=list)
    claims: list[ClaimRecordRead] = Field(default_factory=list)
    artifacts: list[ArtifactSummaryRead] = Field(default_factory=list)
    latest_artifact: DraftArtifactRead | None = None
    events: list[RunEventRead] = Field(default_factory=list)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    terminal_reason: str | None = None


class RunListResponse(BaseModel):
    items: list[RunSummaryRead]
    total: int
    limit: int
    offset: int


class RunCancelResponse(BaseModel):
    run_id: str
    status: RunStatusType
    cancellation_accepted: bool
    message: str


class RunRetryResponse(BaseModel):
    run_id: str
    parent_run_id: str
    status: RunStatusType
    execution_mode: str
    events_url: str


class BenchmarkTopicRead(BaseModel):
    topic_id: str
    category: str
    risk_profile: str
    topic: str
    goal: str
    platform: PlatformType
    audience: str
    depth: DepthType
    expected_risk_notes: str
    is_holdout: bool = False


class BenchmarkCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    dataset_version: str = Field(default="veridra-eval-v1", max_length=64)
    topic_ids: list[str] = Field(default_factory=list, max_length=50)
    topic_count: int = Field(default=6, ge=1, le=30)
    include_holdout: bool = False
    strategies: list[WorkflowStrategyType] = Field(
        default=["single_agent", "multi_agent"], min_length=1, max_length=4
    )
    repeats: int = Field(default=1, ge=1, le=3)
    model_override: str | None = Field(default=None, max_length=120)
    provider_override: str | None = Field(default=None, max_length=40)
    use_demo_mode: bool = False


class BenchmarkCaseRead(BaseModel):
    case_id: str
    topic_id: str
    topic: str
    category: str
    risk_profile: str
    condition: WorkflowStrategyType
    repeat_index: int
    run_id: str | None = None
    status: str
    editor_score: int | None = None
    evidence_coverage: float | None = None
    unsupported_claim_rate: float | None = None
    contradiction_rate: float | None = None
    duration_ms: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None
    cost_status: str = "unavailable"
    revision_count: int = 0
    human_rating: float | None = None
    human_notes: str | None = None


class BenchmarkConditionSummary(BaseModel):
    condition: WorkflowStrategyType
    sample_size: int
    completed_count: int
    failed_count: int
    error_rate: float
    avg_editor_score: float | None = None
    median_editor_score: float | None = None
    avg_evidence_coverage: float | None = None
    avg_unsupported_rate: float | None = None
    avg_contradiction_rate: float | None = None
    median_duration_ms: float | None = None
    p90_duration_ms: float | None = None
    total_tokens: int | None = None
    total_estimated_cost: float | None = None
    cost_per_accepted_artifact: float | None = None
    cost_status: str = "unavailable"
    avg_human_rating: float | None = None
    human_rating_count: int = 0


class BenchmarkDetailRead(BaseModel):
    benchmark_id: str
    name: str
    dataset_version: str
    status: str
    execution_mode: str
    config: dict[str, Any]
    condition_summaries: list[BenchmarkConditionSummary] = Field(default_factory=list)
    cases: list[BenchmarkCaseRead] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at: str
    finished_at: str | None = None


class BenchmarkListResponse(BaseModel):
    items: list[BenchmarkDetailRead]
    total: int
    limit: int
    offset: int


class BenchmarkRatingRequest(BaseModel):
    rating: float = Field(ge=1.0, le=5.0)
    notes: str | None = Field(default=None, max_length=500)


class SupportedModelInfo(BaseModel):
    id: str
    label: str
    provider: str
    tier: str
    description: str
    configured: bool = False
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None


class IntegrationsStatusRead(BaseModel):
    app_env: str
    llm_provider: str
    llm_model: str
    available_models: list[SupportedModelInfo] = Field(default_factory=list)
    llm_configured: bool
    llm_masked_label: str
    configured_providers: list[str] = Field(default_factory=list)
    provider_statuses: dict[str, bool] = Field(default_factory=dict)
    social_connections: dict[str, bool] = Field(default_factory=dict)
    search_provider: str
    search_configured: bool
    search_masked_label: str
    demo_mode_env: bool
    effective_default_mode: str
    database_dialect: str
    langsmith_enabled: bool
    rate_card_version: str
    guardrails: dict[str, int]
    privacy_note: str


class DashboardSummaryRead(BaseModel):
    total_runs: int
    completed_runs: int
    completed_with_warnings_runs: int
    failed_runs: int
    cancelled_runs: int
    active_runs: int
    avg_editor_score: float | None = None
    editor_score_sample_size: int = 0
    avg_evidence_coverage: float | None = None
    total_unsupported_claims: int = 0
    total_contradicted_claims: int = 0
    median_duration_ms: int | None = None
    p90_duration_ms: int | None = None
    total_tokens: int | None = None
    total_estimated_cost: float | None = None
    cost_status: str = "unavailable"
    avg_editor_revisions: float | None = None
    avg_fact_remediations: float | None = None
    provider_health: dict[str, int]
