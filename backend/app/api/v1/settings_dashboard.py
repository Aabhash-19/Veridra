import math
import statistics

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.pricing import RATE_CARD_VERSION, SUPPORTED_AI_MODELS
from app.db.models import NodeMetric, Run
from app.db.session import get_db
from app.schemas.api import DashboardSummaryRead, IntegrationsStatusRead, SupportedModelInfo
from app.services.run_persistence import (
    aggregate_run_metrics,
    build_claims_read,
    compute_run_quality,
)

router = APIRouter(tags=["settings-and-dashboard"])


def _percentile_int(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct
    low = math.floor(idx)
    high = math.ceil(idx)
    if low == high:
        return int(ordered[int(idx)])
    return int(round(ordered[low] + (ordered[high] - ordered[low]) * (idx - low)))


@router.get("/settings/integrations", response_model=IntegrationsStatusRead)
def get_integrations_status() -> IntegrationsStatusRead:
    settings = get_settings()
    statuses = settings.provider_statuses
    llm_ok = settings.is_any_llm_configured
    search_ok = settings.is_tavily_configured

    if settings.demo_mode:
        effective = "demo"
    elif llm_ok:
        effective = "live"
    else:
        effective = "unconfigured_demo_available"

    dialect = "sqlite" if settings.is_sqlite else "postgresql"
    active_provider = settings.active_default_provider
    active_model = settings.active_default_model

    provider_titles = {
        "openai": "ChatGPT",
        "groq": "Groq",
        "openrouter": "OpenRouter",
        "anthropic": "Claude",
        "gemini": "Gemini",
    }
    configured_names = [
        provider_titles.get(p, p.title()) for p in settings.configured_llm_providers
    ]

    return IntegrationsStatusRead(
        app_env=settings.app_env,
        llm_provider=active_provider,
        llm_model=active_model,
        available_models=[
            SupportedModelInfo.model_validate(
                {**m, "configured": bool(statuses.get(str(m["provider"]), False))}
            )
            for m in SUPPORTED_AI_MODELS
        ],
        llm_configured=llm_ok,
        llm_masked_label=(
            f"Ready: {', '.join(configured_names)} ({active_model})"
            if llm_ok
            else "No AI API key configured yet"
        ),
        configured_providers=settings.configured_llm_providers,
        provider_statuses=statuses,
        social_connections=settings.social_connections,
        search_provider=settings.search_provider,
        search_configured=search_ok,
        search_masked_label=(
            "Tavily Search — key configured"
            if search_ok
            else "Tavily Search — API key not configured"
        ),
        demo_mode_env=settings.demo_mode,
        effective_default_mode=effective,
        database_dialect=dialect,
        langsmith_enabled=bool(settings.langsmith_tracing and settings.langsmith_api_key.strip()),
        rate_card_version=RATE_CARD_VERSION,
        guardrails={
            "max_editor_revisions": settings.max_editor_revisions,
            "max_fact_remediations": settings.max_fact_remediations,
            "max_research_retries": settings.max_research_retries,
            "max_graph_steps": settings.max_graph_steps,
            "editor_approval_threshold": settings.editor_approval_threshold,
            "run_timeout_seconds": settings.run_timeout_seconds,
        },
        privacy_note=(
            "Requests, drafts, retrieved source excerpts, claims, and node telemetry are stored "
            "locally in your configured database. Content is sent to external AI/search providers "
            "only when live keys are configured and not in Demo Mode."
        ),
    )


@router.get("/dashboard/summary", response_model=DashboardSummaryRead)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryRead:
    runs = db.scalars(select(Run)).all()
    if not runs:
        return DashboardSummaryRead(
            total_runs=0,
            completed_runs=0,
            completed_with_warnings_runs=0,
            failed_runs=0,
            cancelled_runs=0,
            active_runs=0,
            avg_editor_score=None,
            editor_score_sample_size=0,
            avg_evidence_coverage=None,
            total_unsupported_claims=0,
            total_contradicted_claims=0,
            median_duration_ms=None,
            p90_duration_ms=None,
            total_tokens=None,
            total_estimated_cost=None,
            cost_status="unavailable",
            avg_editor_revisions=None,
            avg_fact_remediations=None,
            provider_health={"rate_limit": 0, "timeout": 0, "other_failure": 0},
        )

    completed = sum(1 for r in runs if r.status == "completed")
    with_warnings = sum(1 for r in runs if r.status == "completed_with_warnings")
    failed = sum(1 for r in runs if r.status == "failed")
    cancelled = sum(1 for r in runs if r.status == "cancelled")
    active = sum(1 for r in runs if r.status in {"queued", "running", "waiting_for_input"})

    editor_scores: list[int] = []
    coverages: list[float] = []
    durations: list[int] = []
    tokens_list: list[int] = []
    costs_list: list[float] = []
    total_unsupported = 0
    total_contradicted = 0

    for r in runs:
        claims = build_claims_read(db, r.id)
        q = compute_run_quality(r, claims)
        if q.editor_score is not None:
            editor_scores.append(q.editor_score)
        if q.evidence_coverage is not None:
            coverages.append(q.evidence_coverage)
        total_unsupported += q.unsupported_claims
        total_contradicted += q.contradicted_claims
        if r.duration_ms is not None:
            durations.append(r.duration_ms)

        m_rows = db.scalars(select(NodeMetric).where(NodeMetric.run_id == r.id)).all()
        m_sum = aggregate_run_metrics(r, m_rows)
        if m_sum.total_tokens is not None:
            tokens_list.append(m_sum.total_tokens)
        if m_sum.estimated_cost is not None:
            costs_list.append(m_sum.estimated_cost)

    all_metrics = db.scalars(select(NodeMetric).where(NodeMetric.status == "failed")).all()
    rate_limit_cnt = sum(1 for m in all_metrics if m.error_code == "PROVIDER_RATE_LIMIT")
    timeout_cnt = sum(1 for m in all_metrics if m.error_code == "PROVIDER_TIMEOUT")
    other_fail_cnt = sum(
        1 for m in all_metrics if m.error_code not in {"PROVIDER_RATE_LIMIT", "PROVIDER_TIMEOUT"}
    )

    return DashboardSummaryRead(
        total_runs=len(runs),
        completed_runs=completed,
        completed_with_warnings_runs=with_warnings,
        failed_runs=failed,
        cancelled_runs=cancelled,
        active_runs=active,
        avg_editor_score=round(statistics.mean(editor_scores), 1) if editor_scores else None,
        editor_score_sample_size=len(editor_scores),
        avg_evidence_coverage=round(statistics.mean(coverages), 4) if coverages else None,
        total_unsupported_claims=total_unsupported,
        total_contradicted_claims=total_contradicted,
        median_duration_ms=_percentile_int(durations, 0.5),
        p90_duration_ms=_percentile_int(durations, 0.9),
        total_tokens=sum(tokens_list) if tokens_list else None,
        total_estimated_cost=round(sum(costs_list), 8) if costs_list else None,
        cost_status="measured_estimated" if costs_list else "unavailable",
        avg_editor_revisions=round(statistics.mean([r.editor_revision_count for r in runs]), 2),
        avg_fact_remediations=round(statistics.mean([r.fact_remediation_count for r in runs]), 2),
        provider_health={
            "rate_limit": rate_limit_cnt,
            "timeout": timeout_cnt,
            "other_failure": other_fail_cnt,
        },
    )
