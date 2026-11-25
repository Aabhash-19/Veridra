from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

PlatformType = Literal["linkedin", "x", "instagram"]
DepthType = Literal["concise", "standard", "deep"]
WorkflowStrategyType = Literal["multi_agent", "single_agent", "no_editor", "no_fact_checker"]
RunStatusType = Literal[
    "queued",
    "running",
    "waiting_for_input",
    "completed",
    "completed_with_warnings",
    "failed",
    "cancelled",
]
SourceStatusType = Literal[
    "retrieved",
    "partially_retrieved",
    "inaccessible",
    "unsupported_content_type",
    "failed",
]
EvidenceRoleType = Literal["supports", "contradicts", "context", "definition", "background"]
ClaimStatusType = Literal[
    "supported",
    "partially_supported",
    "contradicted",
    "unsupported",
    "uncertain",
    "not_checked",
]
ClaimMaterialityType = Literal["high", "medium", "low"]
RecommendedActionType = Literal["keep", "qualify", "correct", "remove"]
EditorVerdictType = Literal["revise", "approve", "blocked"]
FactOverallStatusType = Literal["pass", "pass_with_warnings", "needs_revision", "blocked"]
ArtifactStatusType = Literal["draft", "approved", "partial", "user_edited"]
EventType = Literal[
    "run.queued",
    "run.started",
    "node.started",
    "node.progress",
    "node.completed",
    "node.retrying",
    "run.warning",
    "run.completed",
    "run.failed",
    "run.cancelled",
]
ErrorCodeType = Literal[
    "INVALID_REQUEST",
    "PROVIDER_NOT_CONFIGURED",
    "PROVIDER_RATE_LIMIT",
    "PROVIDER_TIMEOUT",
    "PROVIDER_INVALID_OUTPUT",
    "SEARCH_UNAVAILABLE",
    "INSUFFICIENT_EVIDENCE",
    "RETRY_LIMIT_REACHED",
    "RUN_CANCELLED",
    "INTERNAL_ERROR",
]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class FieldError(BaseModel):
    field: str
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    field_errors: list[FieldError] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorDetail
