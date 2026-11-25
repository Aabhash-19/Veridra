from pydantic import BaseModel, Field, field_validator

from app.schemas.common import (
    ClaimMaterialityType,
    ClaimStatusType,
    EditorVerdictType,
    EvidenceRoleType,
    FactOverallStatusType,
    RecommendedActionType,
)


class ResearchFindingOutput(BaseModel):
    finding: str = Field(min_length=3, max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list)


class ResearchSourceOutput(BaseModel):
    source_id: str = Field(min_length=2, max_length=64)
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=255)
    published_at: str | None = None
    accessed_at: str
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    source_type: str = Field(default="secondary", max_length=64)


class ResearchEvidenceOutput(BaseModel):
    evidence_id: str = Field(min_length=2, max_length=64)
    source_id: str = Field(min_length=2, max_length=64)
    excerpt: str = Field(min_length=5, max_length=2000)
    role: EvidenceRoleType = "supports"
    location_hint: str | None = Field(default=None, max_length=255)
    supports: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ResearchBrief(BaseModel):
    research_summary: str = Field(min_length=10, max_length=4000)
    research_questions: list[str] = Field(default_factory=list, max_length=12)
    key_findings: list[ResearchFindingOutput] = Field(default_factory=list)
    sources: list[ResearchSourceOutput] = Field(default_factory=list)
    evidence_items: list[ResearchEvidenceOutput] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)


class FactualClaimCandidate(BaseModel):
    claim_id: str = Field(min_length=2, max_length=64)
    text: str = Field(min_length=5, max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list)
    materiality: ClaimMaterialityType = "medium"
    claim_type: str = Field(default="factual", max_length=64)


class WriterDraftOutput(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    hook: str = Field(min_length=5, max_length=1000)
    body_markdown: str = Field(min_length=20, max_length=20000)
    outline: list[str] = Field(default_factory=list)
    factual_claims: list[FactualClaimCandidate] = Field(default_factory=list)
    opinion_statements: list[str] = Field(default_factory=list)
    platform_notes: list[str] = Field(default_factory=list)
    thread_segments: list[str] = Field(default_factory=list)
    revision_summary: str | None = Field(default=None, max_length=1500)


class ScoreBreakdown(BaseModel):
    clarity: int = Field(ge=0, le=20)
    depth: int = Field(ge=0, le=20)
    audience: int = Field(ge=0, le=15)
    structure: int = Field(ge=0, le=15)
    platform_fit: int = Field(ge=0, le=15)
    specificity: int = Field(ge=0, le=10)
    tone: int = Field(ge=0, le=5)

    @property
    def computed_total(self) -> int:
        return (
            self.clarity
            + self.depth
            + self.audience
            + self.structure
            + self.platform_fit
            + self.specificity
            + self.tone
        )


class EditorIssue(BaseModel):
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=800)
    suggestion: str = Field(default="", max_length=800)


class EditorResult(BaseModel):
    score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    verdict: EditorVerdictType
    critical_issues: list[str] = Field(default_factory=list)
    major_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)
    rewrite_instructions: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=5, max_length=2000)

    @field_validator("critical_issues", "major_issues", "minor_issues", mode="before")
    @classmethod
    def coerce_issue_dicts(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for item in value:
            if isinstance(item, str):
                normalized.append(item)
            elif isinstance(item, dict):
                desc = item.get("description") or item.get("message") or str(item)
                normalized.append(str(desc))
        return normalized


class EvaluatedClaim(BaseModel):
    claim_id: str = Field(min_length=2, max_length=64)
    claim_text: str = Field(min_length=3, max_length=1500)
    claim_type: str = Field(default="factual", max_length=64)
    materiality: ClaimMaterialityType = "medium"
    status: ClaimStatusType
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=4, max_length=1500)
    recommended_action: RecommendedActionType


class FactCheckResult(BaseModel):
    overall_status: FactOverallStatusType
    claims: list[EvaluatedClaim] = Field(default_factory=list)
    evidence_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    unsupported_count: int = Field(default=0, ge=0)
    contradicted_count: int = Field(default=0, ge=0)
    uncertain_count: int = Field(default=0, ge=0)
    critical_findings: list[str] = Field(default_factory=list)
    rewrite_instructions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class SingleAgentOutput(BaseModel):
    """Structured output for the single-agent baseline comparison mode."""

    draft: WriterDraftOutput
    self_editor_score: int = Field(ge=0, le=100)
    self_editor_breakdown: ScoreBreakdown
    self_editor_summary: str = Field(min_length=5, max_length=1500)
    fact_check: FactCheckResult
