import asyncio
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, run_id_ctx
from app.core.pricing import resolve_effective_provider_and_model
from app.db.models import Project, Run
from app.db.session import get_session_factory
from app.graph.nodes import GraphDependencies
from app.graph.state import VeridraState, WorkflowLimits
from app.graph.workflow import build_veridra_graph
from app.prompts.registry import ensure_prompts_persisted, get_all_prompt_version_tags
from app.providers.base import ProviderError
from app.providers.factory import ProviderBundle, resolve_providers
from app.schemas.api import ContentRequest, NormalizedBrief
from app.schemas.common import new_id, utc_now_iso
from app.services.event_bus import cancellation_registry, event_bus
from app.services.run_persistence import (
    TERMINAL_STATUSES,
    append_run_event,
    update_run_status_safe,
)

logger = get_logger(__name__)

_active_tasks: dict[str, asyncio.Task[None]] = {}


def normalize_request(
    req: ContentRequest,
    project: Project | None = None,
    settings: Settings | None = None,
) -> NormalizedBrief:
    """Merge validated ContentRequest with optional Project defaults into NormalizedBrief."""
    cfg = settings or get_settings()
    proj_defaults = (project.defaults_json or {}) if project is not None else {}

    audience = req.audience or proj_defaults.get("audience") or "Informed practitioners and peers"
    tone = req.tone or proj_defaults.get("tone") or "analytical, clear, professional"
    platform = req.platform or proj_defaults.get("platform") or "linkedin"
    depth = req.depth or proj_defaults.get("depth") or "standard"
    language = req.language or proj_defaults.get("language") or "en"

    req_points = list(req.required_points or proj_defaults.get("required_points") or [])
    proh_points = list(req.prohibited_points or proj_defaults.get("prohibited_points") or [])

    default_lengths = {
        "linkedin": {
            "concise": "120-200 words",
            "standard": "220-380 words",
            "deep": "380-550 words",
        },
        "x": {"concise": "3-4 posts", "standard": "4-6 posts", "deep": "6-8 posts"},
        "instagram": {
            "concise": "80-140 words",
            "standard": "140-220 words",
            "deep": "220-300 words",
        },
    }
    length_hint = req.length_hint or default_lengths.get(platform, {}).get(depth, "220-380 words")
    threshold = req.advanced.editor_threshold or cfg.editor_approval_threshold

    return NormalizedBrief(
        topic=req.topic,
        goal=req.goal,
        platform=platform,
        audience=audience,
        tone=tone,
        depth=depth,
        language=language,
        call_to_action=req.call_to_action,
        constraints=list(req.constraints),
        required_points=req_points,
        prohibited_points=proh_points,
        source_urls=list(req.source_urls),
        source_notes=req.source_notes,
        source_preference=list(req.source_preference),
        length_hint=length_hint,
        workflow_strategy=req.workflow_strategy,
        editor_threshold=threshold,
    )


def create_run_record(
    db: Session,
    *,
    req: ContentRequest,
    execution_mode: str,
    initial_warnings: list[dict[str, Any]],
    parent_run_id: str | None = None,
) -> Run:
    """Create initial Run and run.queued event inside one DB transaction."""
    settings = get_settings()
    ensure_prompts_persisted(db)

    project: Project | None = None
    if req.project_id:
        project = db.get(Project, req.project_id)

    norm = normalize_request(req, project=project, settings=settings)
    run_id = new_id("run")
    now = utc_now_iso()

    run = Run(
        id=run_id,
        project_id=project.id if project is not None else None,
        parent_run_id=parent_run_id,
        status="queued",
        execution_mode=execution_mode,
        workflow_strategy=req.workflow_strategy,
        current_node=None,
        topic=req.topic[:500],
        platform=req.platform,
        request_json=req.model_dump(),
        normalized_brief_json=norm.model_dump(),
        warnings_json=initial_warnings,
        errors_json=[],
        prompt_versions_json=get_all_prompt_version_tags(),
        editor_revision_count=0,
        fact_remediation_count=0,
        research_retry_count=0,
        total_step_count=0,
        cancel_requested=False,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()

    append_run_event(
        db,
        run_id=run_id,
        event_type="run.queued",
        status="queued",
        node=None,
        message=f"Run queued ({execution_mode} mode, {req.workflow_strategy}).",
        safe_payload={"execution_mode": execution_mode, "workflow_strategy": req.workflow_strategy},
        sequence=1,
    )
    db.commit()
    db.refresh(run)
    return run


async def execute_run(
    run_id: str,
    *,
    provider_bundle: ProviderBundle | None = None,
    limits_override: WorkflowLimits | None = None,
) -> None:
    """Execute a persisted run through LangGraph with checkpointing, timeout, and safe error handling."""
    token = run_id_ctx.set(run_id)
    settings = get_settings()
    session_factory = get_session_factory()
    loop = asyncio.get_running_loop()

    try:
        with session_factory() as db:
            run = db.get(Run, run_id)
            if run is None or run.status in TERMINAL_STATUSES:
                return
            req = ContentRequest.model_validate(run.request_json)
            norm = dict(run.normalized_brief_json or {})
            warnings = list(run.warnings_json or [])
            execution_mode = run.execution_mode

        if provider_bundle is None:
            provider_bundle = resolve_providers(
                use_demo_mode=(execution_mode == "demo") or req.use_demo_mode,
                mock_scenario=req.advanced.mock_scenario,
                model_override=req.advanced.model_override,
                provider_override=req.advanced.provider_override,
                settings=settings,
            )

        limits = limits_override or WorkflowLimits(
            max_editor_revisions=settings.max_editor_revisions,
            max_fact_remediations=settings.max_fact_remediations,
            max_research_retries=settings.max_research_retries,
            max_graph_steps=settings.max_graph_steps,
            editor_approval_threshold=req.advanced.editor_threshold
            or settings.editor_approval_threshold,
            max_search_queries=settings.max_search_queries,
            max_sources=settings.max_sources,
            run_timeout_seconds=settings.run_timeout_seconds,
        )

        _, effective_model = resolve_effective_provider_and_model(
            model_override=req.advanced.model_override,
            provider_override=req.advanced.provider_override or provider_bundle.llm.provider_name,
            settings=settings,
        )

        deps = GraphDependencies(
            llm=provider_bundle.llm,
            search=provider_bundle.search,
            model=effective_model,
            temperature=req.advanced.temperature,
            limits=limits,
            session_factory=session_factory,
            loop=loop,
        )

        initial_state: VeridraState = {
            "run_id": run_id,
            "project_id": req.project_id,
            "attempt_id": "att_1",
            "execution_mode": provider_bundle.execution_mode,
            "workflow_strategy": req.workflow_strategy,
            "request": req.model_dump(),
            "normalized_brief": norm,
            "status": "queued",
            "current_node": None,
            "search_plan": [],
            "research_brief": None,
            "sources": [],
            "evidence_items": [],
            "evidence_sufficient": None,
            "search_failed": False,
            "draft": None,
            "latest_artifact_id": None,
            "editor_result": None,
            "editor_revision_count": 0,
            "fact_check_result": None,
            "fact_remediation_count": 0,
            "research_retry_count": 0,
            "total_step_count": 0,
            "revision_mode": None,
            "next_route": None,
            "final_artifact": None,
            "warnings": warnings,
            "errors": [],
            "prompt_versions": get_all_prompt_version_tags(),
            "started_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "terminal_reason": None,
            "cancelled": False,
        }

        graph_config: dict[str, Any] = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": max(30, limits.max_graph_steps + 10),
        }

        if settings.is_sqlite and ":memory:" not in settings.database_url:
            async with AsyncSqliteSaver.from_conn_string(settings.resolved_checkpoint_db) as saver:
                graph = build_veridra_graph(deps, checkpointer=saver)
                await asyncio.wait_for(
                    graph.ainvoke(initial_state, config=graph_config),
                    timeout=limits.run_timeout_seconds,
                )
        else:
            graph = build_veridra_graph(deps)
            await asyncio.wait_for(
                graph.ainvoke(initial_state, config=graph_config),
                timeout=limits.run_timeout_seconds,
            )

    except TimeoutError:
        await _fail_run_safely(
            run_id,
            code="PROVIDER_TIMEOUT",
            message=f"Run exceeded overall timeout ceiling ({settings.run_timeout_seconds}s).",
        )
    except ProviderError as exc:
        await _fail_run_safely(run_id, code=exc.code, message=exc.message)
    except asyncio.CancelledError:
        await _cancel_run_safely(run_id)
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled error in run worker",
            extra={"extra_data": {"error_type": type(exc).__name__}},
        )
        await _fail_run_safely(
            run_id,
            code="INTERNAL_ERROR",
            message="Run encountered an unexpected internal execution error.",
        )
    finally:
        cancellation_registry.clear(run_id)
        _active_tasks.pop(run_id, None)
        run_id_ctx.reset(token)


async def _fail_run_safely(run_id: str, *, code: str, message: str) -> None:
    session_factory = get_session_factory()
    evt_payload: dict[str, Any] | None = None
    with session_factory() as db:
        run = db.get(Run, run_id)
        if run is None or run.status in TERMINAL_STATUSES:
            return
        run.errors_json = [*(run.errors_json or []), {"code": code, "message": message}]
        run.finished_at = utc_now_iso()
        update_run_status_safe(
            db,
            run,
            new_status="failed",
            terminal_reason=code,
        )
        evt = append_run_event(
            db,
            run_id=run_id,
            event_type="run.failed",
            status="failed",
            node=run.current_node,
            message=message,
            safe_payload={"code": code},
        )
        db.commit()
        evt_payload = evt.model_dump()
    if evt_payload:
        await event_bus.publish(run_id, evt_payload)


async def _cancel_run_safely(run_id: str) -> None:
    session_factory = get_session_factory()
    evt_payload: dict[str, Any] | None = None
    with session_factory() as db:
        run = db.get(Run, run_id)
        if run is None or run.status in TERMINAL_STATUSES:
            return
        run.finished_at = utc_now_iso()
        update_run_status_safe(
            db,
            run,
            new_status="cancelled",
            terminal_reason="RUN_CANCELLED",
        )
        evt = append_run_event(
            db,
            run_id=run_id,
            event_type="run.cancelled",
            status="cancelled",
            node=run.current_node,
            message="Run cancelled.",
            safe_payload={"terminal_reason": "RUN_CANCELLED"},
        )
        db.commit()
        evt_payload = evt.model_dump()
    if evt_payload:
        await event_bus.publish(run_id, evt_payload)


def launch_run_background(
    run_id: str,
    *,
    provider_bundle: ProviderBundle | None = None,
) -> asyncio.Task[None]:
    task = asyncio.create_task(
        execute_run(run_id, provider_bundle=provider_bundle),
        name=f"veridra-run-{run_id}",
    )
    _active_tasks[run_id] = task
    return task


async def shutdown_active_runs() -> None:
    tasks = list(_active_tasks.values())
    for run_id in list(_active_tasks.keys()):
        cancellation_registry.request_cancel(run_id)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
