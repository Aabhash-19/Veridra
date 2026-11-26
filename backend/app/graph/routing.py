from typing import Any, Literal

from app.graph.state import VeridraState, WorkflowLimits


def evaluate_evidence_decision(
    state: VeridraState, limits: WorkflowLimits
) -> Literal["writer", "single_agent_run", "researcher", "safe_stop"]:
    """Deterministic routing after evidence_gate."""
    if state.get("cancelled"):
        return "safe_stop"
    if state.get("total_step_count", 0) >= limits.max_graph_steps:
        return "safe_stop"

    if state.get("evidence_sufficient"):
        if state.get("workflow_strategy") == "single_agent":
            return "single_agent_run"
        return "writer"

    # Insufficient evidence: allow bounded research retry once
    if (
        state.get("research_retry_count", 0) <= limits.max_research_retries
        and state.get("next_route") == "researcher"
    ):
        return "researcher"

    return "safe_stop"


def decide_editor_route(
    editor_result: dict[str, Any] | None,
    *,
    editor_revision_count: int,
    total_step_count: int,
    limits: WorkflowLimits,
    threshold_override: int | None = None,
) -> tuple[Literal["fact_checker", "writer", "safe_stop"], str | None]:
    """Pure deterministic editor routing decision.

    Returns (route_target, terminal_reason_if_stop).
    """
    if total_step_count >= limits.max_graph_steps:
        return "safe_stop", "RETRY_LIMIT_REACHED"
    if not editor_result:
        return "safe_stop", "INTERNAL_ERROR"

    threshold = (
        threshold_override if threshold_override is not None else limits.editor_approval_threshold
    )
    score = int(editor_result.get("score") or 0)
    verdict = str(editor_result.get("verdict") or "revise")
    critical_issues = editor_result.get("critical_issues") or []

    if verdict == "blocked":
        return "safe_stop", "EDITORIAL_BLOCKED"

    # Never allow score above threshold to override critical blockers.
    # After at least one completed revision with zero critical blockers and an acceptable score (>= 60),
    # advance to fact_checker rather than looping to a terminal retry failure.
    if len(critical_issues) == 0 and (
        (score >= threshold and verdict == "approve")
        or (editor_revision_count >= 1 and score >= 60)
    ):
        return "fact_checker", None

    if editor_revision_count < limits.max_editor_revisions:
        return "writer", None

    return "safe_stop", "RETRY_LIMIT_REACHED"


def decide_fact_route(
    fact_check_result: dict[str, Any] | None,
    *,
    fact_remediation_count: int,
    total_step_count: int,
    limits: WorkflowLimits,
) -> tuple[Literal["finalizer", "writer", "safe_stop"], str | None]:
    """Pure deterministic fact-check routing decision.

    Returns (route_target, terminal_reason_if_stop).
    """
    if total_step_count >= limits.max_graph_steps:
        return "safe_stop", "RETRY_LIMIT_REACHED"
    if not fact_check_result:
        return "safe_stop", "INTERNAL_ERROR"

    overall = str(fact_check_result.get("overall_status") or "needs_revision")
    contradicted = int(fact_check_result.get("contradicted_count") or 0)
    unsupported = int(fact_check_result.get("unsupported_count") or 0)

    if overall == "blocked":
        return "safe_stop", "FACT_CHECK_BLOCKED"

    # Contradicted or unsupported material claims require writer remediation while budget remains
    if contradicted > 0 or unsupported > 0:
        if fact_remediation_count < limits.max_fact_remediations:
            return "writer", None
        return "safe_stop", "RETRY_LIMIT_REACHED"

    # All material claims are supported, partially_supported, or explicitly uncertain/not_checked
    return "finalizer", None
