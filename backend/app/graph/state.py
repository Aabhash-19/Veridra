from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass(frozen=True)
class WorkflowLimits:
    max_editor_revisions: int = 3
    max_fact_remediations: int = 2
    max_research_retries: int = 1
    max_graph_steps: int = 24
    editor_approval_threshold: int = 75
    max_search_queries: int = 6
    max_sources: int = 12
    run_timeout_seconds: int = 600


class VeridraState(TypedDict):
    run_id: str
    project_id: str | None
    attempt_id: str
    execution_mode: str
    workflow_strategy: str
    request: dict[str, Any]
    normalized_brief: dict[str, Any]
    status: str
    current_node: str | None

    search_plan: list[dict[str, Any]]
    research_brief: dict[str, Any] | None
    sources: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    evidence_sufficient: bool | None
    search_failed: bool

    draft: dict[str, Any] | None
    latest_artifact_id: str | None
    editor_result: dict[str, Any] | None
    editor_revision_count: int
    fact_check_result: dict[str, Any] | None
    fact_remediation_count: int
    research_retry_count: int
    total_step_count: int
    revision_mode: str | None

    next_route: str | None
    final_artifact: dict[str, Any] | None
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    prompt_versions: dict[str, str]
    started_at: str
    updated_at: str
    terminal_reason: str | None
    cancelled: bool
