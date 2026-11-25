import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agents.editor import run_editor_agent
from app.agents.fact_checker import run_fact_checker_agent
from app.agents.researcher import run_researcher_agent
from app.agents.single_agent import run_single_agent_baseline
from app.agents.writer import run_writer_agent
from app.core.logging import get_logger
from app.core.pricing import calculate_node_cost, resolve_live_gemini_model
from app.db.models import Run
from app.graph.routing import decide_editor_route, decide_fact_route
from app.graph.state import VeridraState, WorkflowLimits
from app.prompts.registry import get_all_prompt_version_tags
from app.providers.base import LLMProvider, ProviderError, SearchProvider
from app.schemas.common import utc_now_iso
from app.services.event_bus import cancellation_registry, event_bus
from app.services.run_persistence import (
    TERMINAL_STATUSES,
    append_run_event,
    create_artifact_version,
    persist_claims_ledger,
    persist_sources_and_evidence,
    record_node_metric,
    save_checkpoint_snapshot,
    update_run_status_safe,
)

logger = get_logger(__name__)


def _node_model(raw_model: str | None, provider_name: str) -> str:
    cleaned = (raw_model or "").strip()
    if provider_name == "gemini":
        return resolve_live_gemini_model(cleaned)
    return cleaned or "mock"


@dataclass(slots=True)
class GraphDependencies:
    llm: LLMProvider
    search: SearchProvider | None
    model: str
    temperature: float
    limits: WorkflowLimits
    session_factory: Callable[[], Session]
    loop: asyncio.AbstractEventLoop | None = None


def _emit_sync(
    deps: GraphDependencies,
    *,
    run_id: str,
    attempt_id: str,
    event_type: str,
    status: str,
    message: str,
    node: str | None = None,
    safe_payload: dict[str, Any] | None = None,
) -> None:
    with deps.session_factory() as db:
        evt = append_run_event(
            db,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type=event_type,
            status=status,
            message=message,
            node=node,
            safe_payload=safe_payload,
        )
        db.commit()
    payload = evt.model_dump()
    if deps.loop and deps.loop.is_running():
        asyncio.run_coroutine_threadsafe(event_bus.publish(run_id, payload), deps.loop)


async def _emit(
    deps: GraphDependencies,
    *,
    run_id: str,
    attempt_id: str,
    event_type: str,
    status: str,
    message: str,
    node: str | None = None,
    safe_payload: dict[str, Any] | None = None,
) -> None:
    with deps.session_factory() as db:
        evt = append_run_event(
            db,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type=event_type,
            status=status,
            message=message,
            node=node,
            safe_payload=safe_payload,
        )
        db.commit()
    await event_bus.publish(run_id, evt.model_dump())


def _is_cancelled(deps: GraphDependencies, run_id: str) -> bool:
    if cancellation_registry.is_cancelled(run_id):
        return True
    with deps.session_factory() as db:
        run = db.get(Run, run_id)
        return bool(run and run.cancel_requested)


def _save_run_progress(
    deps: GraphDependencies,
    run_id: str,
    *,
    current_node: str | None = None,
    status: str | None = None,
    checkpoint_key: str | None = None,
    state_snapshot: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
) -> None:
    with deps.session_factory() as db:
        run = db.get(Run, run_id)
        if run is None:
            return
        if status and run.status not in TERMINAL_STATUSES:
            update_run_status_safe(db, run, new_status=status, current_node=current_node)
        elif current_node and run.status not in TERMINAL_STATUSES:
            run.current_node = current_node
            run.updated_at = utc_now_iso()
        if fields:
            for k, v in fields.items():
                setattr(run, k, v)
        if checkpoint_key and state_snapshot is not None:
            save_checkpoint_snapshot(
                db,
                run_id=run_id,
                checkpoint_key=checkpoint_key,
                state_snapshot=state_snapshot,
            )
        db.commit()


def _format_final_markdown(
    *,
    draft: dict[str, Any],
    sources: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    body = str(draft.get("body_markdown") or "").strip()
    usable_sources = [s for s in sources if s.get("status") in {"retrieved", "partially_retrieved"}]

    lines = [body]
    if usable_sources and "## Sources" not in body and "Sources:" not in body:
        lines.append("")
        lines.append("## Sources")
        for src in usable_sources[:5]:
            raw_title = str(src.get("title") or src["url"]).strip()
            clean_title = raw_title[:80].rstrip(" -–—|:") + ("..." if len(raw_title) > 80 else "")
            pub = str(src.get("publisher") or "").strip()
            label = f"{clean_title} ({pub})" if pub and pub.lower() not in clean_title.lower() else clean_title
            lines.append(f"- [{label}]({src['url']})")

    non_demo_warnings = [w for w in warnings if w.get("code") != "DEMO_MODE"]
    if non_demo_warnings and "## Evidence Notes" not in body:
        lines.append("")
        lines.append("## Evidence Notes")
        for w in non_demo_warnings:
            lines.append(f"- {w.get('message')}")

    return "\n".join(lines).strip()


def make_nodes(deps: GraphDependencies) -> dict[str, Any]:
    """Create explicit LangGraph node callables bound to GraphDependencies."""

    async def initialize_run(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        started_at = utc_now_iso()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        prompt_versions = get_all_prompt_version_tags()
        _save_run_progress(
            deps,
            run_id,
            current_node="initialize_run",
            status="running",
            checkpoint_key="step_0_initialize",
            state_snapshot={"step": "initialize_run", "status": "running"},
            fields={
                "started_at": started_at,
                "prompt_versions_json": prompt_versions,
                "normalized_brief_json": state["normalized_brief"],
            },
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="run.started",
            status="running",
            node="initialize_run",
            message=f"Workflow started ({state['workflow_strategy']}, {state['execution_mode']} mode).",
            safe_payload={
                "workflow_strategy": state["workflow_strategy"],
                "execution_mode": state["execution_mode"],
            },
        )
        return {
            "status": "running",
            "current_node": "initialize_run",
            "prompt_versions": prompt_versions,
            "started_at": started_at,
            "updated_at": started_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def plan_research(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        t0 = time.monotonic()
        started_at = utc_now_iso()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.started",
            status="running",
            node="plan_research",
            message="Planning targeted search queries and source scope.",
        )

        brief = state["normalized_brief"]
        topic = str(brief.get("topic") or "").strip()
        audience = str(brief.get("audience") or "").strip()
        req_points = [
            str(p).strip() for p in (brief.get("required_points") or []) if str(p).strip()
        ]
        time_scope = (state.get("request", {}).get("advanced") or {}).get("time_scope")

        queries: list[dict[str, Any]] = [
            {"query": topic[:140], "intent": "primary_overview", "priority": 1},
        ]
        if req_points:
            queries.append(
                {
                    "query": f"{topic[:90]} {' '.join(req_points[:2])}"[:160],
                    "intent": "required_points",
                    "priority": 2,
                }
            )
        else:
            queries.append(
                {
                    "query": f"{topic[:100]} evidence examples analysis"[:160],
                    "intent": "supporting_evidence",
                    "priority": 2,
                }
            )
        if audience and len(queries) < deps.limits.max_search_queries:
            queries.append(
                {
                    "query": f"{topic[:90]} {audience[:40]}"[:150],
                    "intent": "audience_context",
                    "priority": 3,
                }
            )
        if time_scope:
            queries[0]["freshness"] = time_scope

        ended_at = utc_now_iso()
        latency_ms = int((time.monotonic() - t0) * 1000)
        with deps.session_factory() as db:
            record_node_metric(
                db,
                run_id=run_id,
                node="plan_research",
                attempt=1,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                status="completed",
            )
            db.commit()

        _save_run_progress(
            deps,
            run_id,
            current_node="plan_research",
            checkpoint_key="step_1_plan_research",
            state_snapshot={"search_plan_count": len(queries)},
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="plan_research",
            message=f"Prepared {len(queries)} targeted research queries.",
            safe_payload={"query_count": len(queries)},
        )
        return {
            "search_plan": queries,
            "current_node": "plan_research",
            "updated_at": ended_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def researcher(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        retry_num = state.get("research_retry_count", 0)
        attempt = retry_num + 1
        started_at = utc_now_iso()
        t0 = time.monotonic()

        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.started",
            status="running",
            node="researcher",
            message=(
                "Retrying research with broadened queries."
                if retry_num > 0
                else "Collecting relevant public sources and extracting evidence."
            ),
            safe_payload={"attempt": attempt},
        )

        search_plan = list(state.get("search_plan") or [])
        if retry_num > 0:
            topic = str(state["normalized_brief"].get("topic") or "")
            search_plan = [
                {"query": f"{topic[:100]} overview guide", "intent": "retry_broad", "priority": 1},
                {
                    "query": f"{topic[:100]} official documentation",
                    "intent": "retry_primary",
                    "priority": 2,
                },
            ]

        adv = state.get("request", {}).get("advanced") or {}
        try:
            res = await run_researcher_agent(
                normalized_brief=state["normalized_brief"],
                search_plan=search_plan,
                llm=deps.llm,
                search=deps.search,
                model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                temperature=float(adv.get("temperature", deps.temperature)),
                max_sources=deps.limits.max_sources,
                search_depth=str(adv.get("search_depth") or "advanced"),
                time_scope=adv.get("time_scope"),
                previous_brief=state.get("research_brief"),
                trace_context={"run_id": run_id, "attempt": attempt},
            )
        except ProviderError as exc:
            ended_at = utc_now_iso()
            latency_ms = int((time.monotonic() - t0) * 1000)
            with deps.session_factory() as db:
                record_node_metric(
                    db,
                    run_id=run_id,
                    node="researcher",
                    attempt=attempt,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=latency_ms,
                    provider=deps.llm.provider_name,
                    model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                    status="failed",
                    error_code=exc.code,
                )
                db.commit()
            return {
                "errors": [
                    *state.get("errors", []),
                    {"code": exc.code, "message": exc.message, "node": "researcher"},
                ],
                "terminal_reason": exc.code,
                "next_route": "safe_stop",
                "updated_at": ended_at,
            }

        ended_at = utc_now_iso()
        latency_ms = int((time.monotonic() - t0) * 1000)
        llm_res = res.llm_result
        cost = calculate_node_cost(
            provider=llm_res.provider,
            model=llm_res.model,
            prompt_tokens=llm_res.prompt_tokens,
            completion_tokens=llm_res.completion_tokens,
        )

        brief_dict = res.research_brief.model_dump()
        merged_warnings = list(state.get("warnings") or [])
        seen_msgs = {(w.get("code"), w.get("message")) for w in merged_warnings}
        for w in res.warnings:
            if (w.get("code"), w.get("message")) not in seen_msgs:
                merged_warnings.append(w)
                seen_msgs.add((w.get("code"), w.get("message")))

        with deps.session_factory() as db:
            persist_sources_and_evidence(
                db,
                run_id=run_id,
                sources=res.sources,
                evidence_items=res.evidence_items,
            )
            record_node_metric(
                db,
                run_id=run_id,
                node="researcher",
                attempt=attempt,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                model_latency_ms=llm_res.latency_ms,
                tool_latency_ms=res.tool_latency_ms,
                provider=llm_res.provider,
                model=llm_res.model,
                input_tokens=llm_res.prompt_tokens,
                output_tokens=llm_res.completion_tokens,
                total_tokens=llm_res.total_tokens,
                cost_dict=cost.to_dict(),
                tool_calls=res.tool_calls,
                prompt_version=res.prompt_version,
                status="completed",
            )
            db.commit()

        _save_run_progress(
            deps,
            run_id,
            current_node="researcher",
            checkpoint_key=f"step_researcher_{attempt}",
            state_snapshot={
                "sources_count": len(res.sources),
                "evidence_count": len(res.evidence_items),
            },
            fields={
                "research_brief_json": brief_dict,
                "warnings_json": merged_warnings,
            },
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="researcher",
            message=f"Collected {len(res.sources)} source(s) and {len(res.evidence_items)} evidence item(s).",
            safe_payload={
                "sources_found": len(res.sources),
                "evidence_count": len(res.evidence_items),
                "attempt": attempt,
            },
        )
        return {
            "research_brief": brief_dict,
            "sources": res.sources,
            "evidence_items": res.evidence_items,
            "search_failed": res.search_failed,
            "warnings": merged_warnings,
            "current_node": "researcher",
            "updated_at": ended_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def evidence_gate(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        now = utc_now_iso()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": now}

        sources = state.get("sources") or []
        evidence_items = state.get("evidence_items") or []
        usable_sources = [
            s for s in sources if s.get("status") in {"retrieved", "partially_retrieved"}
        ]
        user_notes = (state.get("normalized_brief") or {}).get("source_notes")
        search_failed = bool(state.get("search_failed"))
        retry_count = state.get("research_retry_count", 0)

        sufficient = False
        next_route = "safe_stop"
        terminal_reason: str | None = None
        new_retry_count = retry_count
        warnings = list(state.get("warnings") or [])

        if len(usable_sources) >= 2 and len(evidence_items) >= 2:
            sufficient = True
            next_route = (
                "single_agent_run" if state.get("workflow_strategy") == "single_agent" else "writer"
            )
        elif (
            len(usable_sources) >= 1
            and len(evidence_items) >= 1
            and (search_failed or retry_count >= deps.limits.max_research_retries)
        ):
            sufficient = True
            next_route = (
                "single_agent_run" if state.get("workflow_strategy") == "single_agent" else "writer"
            )
            warnings.append(
                {
                    "code": "LIMITED_EVIDENCE",
                    "message": "Proceeding with limited source corroboration; claims must remain narrowly qualified.",
                    "node": "evidence_gate",
                }
            )
        elif search_failed and user_notes and len(str(user_notes).strip()) >= 30:
            sufficient = True
            next_route = (
                "single_agent_run" if state.get("workflow_strategy") == "single_agent" else "writer"
            )
            warnings.append(
                {
                    "code": "USER_NOTES_ONLY",
                    "message": "Search unavailable; drafting strictly from user-supplied notes without external web corroboration.",
                    "node": "evidence_gate",
                }
            )
        elif retry_count < deps.limits.max_research_retries and not search_failed:
            new_retry_count = retry_count + 1
            sufficient = False
            next_route = "researcher"
            _save_run_progress(
                deps,
                run_id,
                current_node="evidence_gate",
                fields={"research_retry_count": new_retry_count},
            )
            await _emit(
                deps,
                run_id=run_id,
                attempt_id=attempt_id,
                event_type="node.retrying",
                status="retrying",
                node="evidence_gate",
                message=f"Evidence coverage is weak; running bounded research retry {new_retry_count} of {deps.limits.max_research_retries}.",
                safe_payload={"research_retry_count": new_retry_count},
            )
            return {
                "evidence_sufficient": False,
                "research_retry_count": new_retry_count,
                "next_route": "researcher",
                "current_node": "evidence_gate",
                "updated_at": now,
                "total_step_count": state.get("total_step_count", 0) + 1,
            }
        else:
            sufficient = False
            next_route = "safe_stop"
            terminal_reason = "INSUFFICIENT_EVIDENCE"
            warnings.append(
                {
                    "code": "INSUFFICIENT_EVIDENCE",
                    "message": "Insufficient credible evidence collected after bounded research budget; stopped safely without fabricating claims.",
                    "node": "evidence_gate",
                }
            )

        _save_run_progress(
            deps,
            run_id,
            current_node="evidence_gate",
            checkpoint_key="step_evidence_gate",
            state_snapshot={"evidence_sufficient": sufficient, "next_route": next_route},
            fields={"warnings_json": warnings, "research_retry_count": new_retry_count},
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed" if sufficient else "run.warning",
            status="completed" if sufficient else "warning",
            node="evidence_gate",
            message=(
                f"Evidence gate passed ({len(usable_sources)} usable sources)."
                if sufficient
                else "Evidence gate stopped run safely: insufficient retrieved sources."
            ),
            safe_payload={"evidence_sufficient": sufficient, "usable_sources": len(usable_sources)},
        )
        return {
            "evidence_sufficient": sufficient,
            "next_route": next_route,
            "terminal_reason": terminal_reason,
            "warnings": warnings,
            "current_node": "evidence_gate",
            "updated_at": now,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def writer(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        started_at = utc_now_iso()
        t0 = time.monotonic()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        rev_mode = state.get("revision_mode")
        attempt = 1 + state.get("editor_revision_count", 0) + state.get("fact_remediation_count", 0)
        msg = (
            f"Revising draft from Editor feedback (Revision {state.get('editor_revision_count', 0)} of {deps.limits.max_editor_revisions})."
            if rev_mode == "editor"
            else (
                f"Remediating flagged claims from Fact Checker (Attempt {state.get('fact_remediation_count', 0)} of {deps.limits.max_fact_remediations})."
                if rev_mode == "fact_check"
                else "Drafting structured post grounded in research brief."
            )
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.started",
            status="running",
            node="writer",
            message=msg,
            safe_payload={"attempt": attempt, "revision_mode": rev_mode},
        )

        adv = state.get("request", {}).get("advanced") or {}
        try:
            res = await run_writer_agent(
                normalized_brief=state["normalized_brief"],
                research_brief=state.get("research_brief") or {},
                evidence_items=state.get("evidence_items") or [],
                llm=deps.llm,
                model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                temperature=float(adv.get("temperature", deps.temperature)),
                prior_draft=state.get("draft"),
                editor_result=state.get("editor_result"),
                fact_check_result=state.get("fact_check_result"),
                revision_mode=rev_mode,
                trace_context={"run_id": run_id, "attempt": attempt},
            )
        except ProviderError as exc:
            ended_at = utc_now_iso()
            latency_ms = int((time.monotonic() - t0) * 1000)
            with deps.session_factory() as db:
                record_node_metric(
                    db,
                    run_id=run_id,
                    node="writer",
                    attempt=attempt,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=latency_ms,
                    provider=deps.llm.provider_name,
                    model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                    status="failed",
                    error_code=exc.code,
                )
                db.commit()
            return {
                "errors": [
                    *state.get("errors", []),
                    {"code": exc.code, "message": exc.message, "node": "writer"},
                ],
                "terminal_reason": exc.code,
                "next_route": "safe_stop",
                "updated_at": ended_at,
            }

        ended_at = utc_now_iso()
        latency_ms = int((time.monotonic() - t0) * 1000)
        draft_dict = res.draft.model_dump()
        llm_res = res.llm_result
        cost = calculate_node_cost(
            provider=llm_res.provider,
            model=llm_res.model,
            prompt_tokens=llm_res.prompt_tokens,
            completion_tokens=llm_res.completion_tokens,
        )

        with deps.session_factory() as db:
            art = create_artifact_version(
                db,
                run_id=run_id,
                title=res.draft.title,
                hook=res.draft.hook,
                body_markdown=res.draft.body_markdown,
                platform=state["normalized_brief"]["platform"],
                outline=res.draft.outline,
                thread_segments=res.draft.thread_segments,
                created_by="writer",
                status="draft",
                parent_version_id=state.get("latest_artifact_id"),
                is_agent_approved=False,
            )
            record_node_metric(
                db,
                run_id=run_id,
                node="writer",
                attempt=attempt,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                model_latency_ms=llm_res.latency_ms,
                provider=llm_res.provider,
                model=llm_res.model,
                input_tokens=llm_res.prompt_tokens,
                output_tokens=llm_res.completion_tokens,
                total_tokens=llm_res.total_tokens,
                cost_dict=cost.to_dict(),
                prompt_version=res.prompt_version,
                status="completed",
            )
            db.commit()
            art_id = art.id
            art_ver = art.version

        _save_run_progress(
            deps,
            run_id,
            current_node="writer",
            checkpoint_key=f"step_writer_{attempt}",
            state_snapshot={"artifact_version": art_ver},
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="writer",
            message=f"Saved draft version {art_ver} ({len(res.draft.factual_claims)} factual claim candidate(s)).",
            safe_payload={
                "artifact_version": art_ver,
                "claim_count": len(res.draft.factual_claims),
            },
        )
        return {
            "draft": draft_dict,
            "latest_artifact_id": art_id,
            "current_node": "writer",
            "updated_at": ended_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def editor(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        started_at = utc_now_iso()
        t0 = time.monotonic()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        attempt = 1 + state.get("editor_revision_count", 0)
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.started",
            status="running",
            node="editor",
            message="Scoring draft structure, clarity, audience fit, and tone.",
            safe_payload={"attempt": attempt},
        )

        adv = state.get("request", {}).get("advanced") or {}
        threshold = int(
            adv.get("editor_threshold")
            or state["normalized_brief"].get("editor_threshold")
            or deps.limits.editor_approval_threshold
        )
        try:
            res = await run_editor_agent(
                normalized_brief=state["normalized_brief"],
                draft=state.get("draft") or {},
                prior_feedback=state.get("editor_result"),
                llm=deps.llm,
                model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                threshold=threshold,
                temperature=0.1,
                trace_context={"run_id": run_id, "attempt": attempt},
            )
        except ProviderError as exc:
            ended_at = utc_now_iso()
            latency_ms = int((time.monotonic() - t0) * 1000)
            with deps.session_factory() as db:
                record_node_metric(
                    db,
                    run_id=run_id,
                    node="editor",
                    attempt=attempt,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=latency_ms,
                    provider=deps.llm.provider_name,
                    model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                    status="failed",
                    error_code=exc.code,
                )
                db.commit()
            return {
                "errors": [
                    *state.get("errors", []),
                    {"code": exc.code, "message": exc.message, "node": "editor"},
                ],
                "terminal_reason": exc.code,
                "next_route": "safe_stop",
                "updated_at": ended_at,
            }

        ended_at = utc_now_iso()
        latency_ms = int((time.monotonic() - t0) * 1000)
        ed_dict = res.editor_result.model_dump()
        llm_res = res.llm_result
        cost = calculate_node_cost(
            provider=llm_res.provider,
            model=llm_res.model,
            prompt_tokens=llm_res.prompt_tokens,
            completion_tokens=llm_res.completion_tokens,
        )

        with deps.session_factory() as db:
            record_node_metric(
                db,
                run_id=run_id,
                node="editor",
                attempt=attempt,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                model_latency_ms=llm_res.latency_ms,
                provider=llm_res.provider,
                model=llm_res.model,
                input_tokens=llm_res.prompt_tokens,
                output_tokens=llm_res.completion_tokens,
                total_tokens=llm_res.total_tokens,
                cost_dict=cost.to_dict(),
                prompt_version=res.prompt_version,
                status="completed",
            )
            db.commit()

        _save_run_progress(
            deps,
            run_id,
            current_node="editor",
            checkpoint_key=f"step_editor_{attempt}",
            state_snapshot={"score": ed_dict["score"], "verdict": ed_dict["verdict"]},
            fields={"editor_result_json": ed_dict},
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="editor",
            message=f"Editorial review scored {ed_dict['score']}/100 ({ed_dict['verdict']}).",
            safe_payload={"score": ed_dict["score"], "verdict": ed_dict["verdict"]},
        )
        return {
            "editor_result": ed_dict,
            "current_node": "editor",
            "updated_at": ended_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def editor_router(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        now = utc_now_iso()
        if _is_cancelled(deps, run_id):
            return {
                "cancelled": True,
                "terminal_reason": "RUN_CANCELLED",
                "next_route": "safe_stop",
                "updated_at": now,
            }

        if state.get("next_route") == "safe_stop" and state.get("errors"):
            return {"next_route": "safe_stop", "updated_at": now}

        rev_count = state.get("editor_revision_count", 0)
        steps = state.get("total_step_count", 0)
        adv = state.get("request", {}).get("advanced") or {}
        threshold = adv.get("editor_threshold") or state["normalized_brief"].get("editor_threshold")
        raw_route, reason = decide_editor_route(
            state.get("editor_result"),
            editor_revision_count=rev_count,
            total_step_count=steps,
            limits=deps.limits,
            threshold_override=int(threshold) if threshold is not None else None,
        )
        route: str = raw_route

        if route == "fact_checker" and state.get("workflow_strategy") == "no_fact_checker":
            route = "finalizer"

        if route == "writer":
            new_rev = rev_count + 1
            _save_run_progress(
                deps,
                run_id,
                current_node="editor_router",
                fields={"editor_revision_count": new_rev},
            )
            await _emit(
                deps,
                run_id=run_id,
                attempt_id=attempt_id,
                event_type="node.retrying",
                status="retrying",
                node="editor_router",
                message=f"Routing draft back to Writer for editorial Revision {new_rev} of {deps.limits.max_editor_revisions}.",
                safe_payload={"editor_revision_count": new_rev},
            )
            return {
                "editor_revision_count": new_rev,
                "revision_mode": "editor",
                "next_route": "writer",
                "current_node": "editor_router",
                "updated_at": now,
                "total_step_count": steps + 1,
            }

        if route == "safe_stop":
            warnings = list(state.get("warnings") or [])
            warnings.append(
                {
                    "code": reason or "RETRY_LIMIT_REACHED",
                    "message": (
                        f"Editorial revision cap ({deps.limits.max_editor_revisions}) reached or blocked before approval."
                    ),
                    "node": "editor_router",
                }
            )
            _save_run_progress(
                deps,
                run_id,
                current_node="editor_router",
                fields={"warnings_json": warnings},
            )
            await _emit(
                deps,
                run_id=run_id,
                attempt_id=attempt_id,
                event_type="run.warning",
                status="warning",
                node="editor_router",
                message="Editor loop stopped at safety ceiling; preserving latest draft as partial.",
                safe_payload={"terminal_reason": reason},
            )
            return {
                "next_route": "safe_stop",
                "terminal_reason": reason or "RETRY_LIMIT_REACHED",
                "warnings": warnings,
                "current_node": "editor_router",
                "updated_at": now,
                "total_step_count": steps + 1,
            }

        return {
            "next_route": route,
            "revision_mode": None,
            "current_node": "editor_router",
            "updated_at": now,
            "total_step_count": steps + 1,
        }

    async def fact_checker(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        started_at = utc_now_iso()
        t0 = time.monotonic()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        attempt = 1 + state.get("fact_remediation_count", 0)
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.started",
            status="running",
            node="fact_checker",
            message="Comparing material factual claims against collected sources.",
            safe_payload={"attempt": attempt},
        )

        adv = state.get("request", {}).get("advanced") or {}
        try:
            res = await run_fact_checker_agent(
                normalized_brief=state["normalized_brief"],
                draft=state.get("draft") or {},
                sources=state.get("sources") or [],
                evidence_items=state.get("evidence_items") or [],
                llm=deps.llm,
                model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                temperature=0.0,
                trace_context={"run_id": run_id, "attempt": attempt},
            )
        except ProviderError as exc:
            ended_at = utc_now_iso()
            latency_ms = int((time.monotonic() - t0) * 1000)
            with deps.session_factory() as db:
                record_node_metric(
                    db,
                    run_id=run_id,
                    node="fact_checker",
                    attempt=attempt,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=latency_ms,
                    provider=deps.llm.provider_name,
                    model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                    status="failed",
                    error_code=exc.code,
                )
                db.commit()
            return {
                "errors": [
                    *state.get("errors", []),
                    {"code": exc.code, "message": exc.message, "node": "fact_checker"},
                ],
                "terminal_reason": exc.code,
                "next_route": "safe_stop",
                "updated_at": ended_at,
            }

        ended_at = utc_now_iso()
        latency_ms = int((time.monotonic() - t0) * 1000)
        fc_dict = res.fact_check_result.model_dump()
        llm_res = res.llm_result
        cost = calculate_node_cost(
            provider=llm_res.provider,
            model=llm_res.model,
            prompt_tokens=llm_res.prompt_tokens,
            completion_tokens=llm_res.completion_tokens,
        )

        with deps.session_factory() as db:
            persist_claims_ledger(
                db,
                run_id=run_id,
                artifact_id=state.get("latest_artifact_id"),
                claims=fc_dict.get("claims", []),
            )
            record_node_metric(
                db,
                run_id=run_id,
                node="fact_checker",
                attempt=attempt,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                model_latency_ms=llm_res.latency_ms,
                provider=llm_res.provider,
                model=llm_res.model,
                input_tokens=llm_res.prompt_tokens,
                output_tokens=llm_res.completion_tokens,
                total_tokens=llm_res.total_tokens,
                cost_dict=cost.to_dict(),
                prompt_version=res.prompt_version,
                status="completed",
            )
            db.commit()

        _save_run_progress(
            deps,
            run_id,
            current_node="fact_checker",
            checkpoint_key=f"step_fact_checker_{attempt}",
            state_snapshot={
                "overall_status": fc_dict["overall_status"],
                "unsupported_count": fc_dict["unsupported_count"],
                "contradicted_count": fc_dict["contradicted_count"],
            },
            fields={"fact_check_result_json": fc_dict},
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="fact_checker",
            message=(
                f"Evidence check: {fc_dict['overall_status']} "
                f"(coverage {int((fc_dict.get('evidence_coverage') or 0) * 100)}%, "
                f"{fc_dict['unsupported_count']} unsupported, {fc_dict['contradicted_count']} contradicted)."
            ),
            safe_payload={
                "overall_status": fc_dict["overall_status"],
                "evidence_coverage": fc_dict["evidence_coverage"],
                "unsupported_count": fc_dict["unsupported_count"],
                "contradicted_count": fc_dict["contradicted_count"],
                "uncertain_count": fc_dict["uncertain_count"],
            },
        )
        return {
            "fact_check_result": fc_dict,
            "current_node": "fact_checker",
            "updated_at": ended_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def fact_router(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        now = utc_now_iso()
        if _is_cancelled(deps, run_id):
            return {
                "cancelled": True,
                "terminal_reason": "RUN_CANCELLED",
                "next_route": "safe_stop",
                "updated_at": now,
            }

        if state.get("next_route") == "safe_stop" and state.get("errors"):
            return {"next_route": "safe_stop", "updated_at": now}

        rem_count = state.get("fact_remediation_count", 0)
        steps = state.get("total_step_count", 0)
        route, reason = decide_fact_route(
            state.get("fact_check_result"),
            fact_remediation_count=rem_count,
            total_step_count=steps,
            limits=deps.limits,
        )

        if route == "writer":
            new_rem = rem_count + 1
            _save_run_progress(
                deps,
                run_id,
                current_node="fact_router",
                fields={"fact_remediation_count": new_rem},
            )
            await _emit(
                deps,
                run_id=run_id,
                attempt_id=attempt_id,
                event_type="node.retrying",
                status="retrying",
                node="fact_router",
                message=f"Routing draft back to Writer for claim remediation {new_rem} of {deps.limits.max_fact_remediations}.",
                safe_payload={"fact_remediation_count": new_rem},
            )
            return {
                "fact_remediation_count": new_rem,
                "revision_mode": "fact_check",
                "next_route": "writer",
                "current_node": "fact_router",
                "updated_at": now,
                "total_step_count": steps + 1,
            }

        if route == "safe_stop":
            warnings = list(state.get("warnings") or [])
            warnings.append(
                {
                    "code": reason or "RETRY_LIMIT_REACHED",
                    "message": (
                        "Unsupported or contradicted material claims could not be resolved within the remediation limit."
                    ),
                    "node": "fact_router",
                }
            )
            _save_run_progress(
                deps,
                run_id,
                current_node="fact_router",
                fields={"warnings_json": warnings},
            )
            await _emit(
                deps,
                run_id=run_id,
                attempt_id=attempt_id,
                event_type="run.warning",
                status="warning",
                node="fact_router",
                message="Fact-check remediation limit reached with unresolved claims; stopping safely.",
                safe_payload={"terminal_reason": reason},
            )
            return {
                "next_route": "safe_stop",
                "terminal_reason": reason or "RETRY_LIMIT_REACHED",
                "warnings": warnings,
                "current_node": "fact_router",
                "updated_at": now,
                "total_step_count": steps + 1,
            }

        return {
            "next_route": "finalizer",
            "revision_mode": None,
            "current_node": "fact_router",
            "updated_at": now,
            "total_step_count": steps + 1,
        }

    async def single_agent_run(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        started_at = utc_now_iso()
        t0 = time.monotonic()
        if _is_cancelled(deps, run_id):
            return {
                "cancelled": True,
                "terminal_reason": "RUN_CANCELLED",
                "next_route": "safe_stop",
                "updated_at": started_at,
            }

        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.started",
            status="running",
            node="single_agent_run",
            message="Running single-agent baseline synthesis and self-check.",
        )

        adv = state.get("request", {}).get("advanced") or {}
        try:
            res = await run_single_agent_baseline(
                normalized_brief=state["normalized_brief"],
                research_brief=state.get("research_brief") or {},
                evidence_items=state.get("evidence_items") or [],
                llm=deps.llm,
                model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                temperature=float(adv.get("temperature", deps.temperature)),
                trace_context={"run_id": run_id, "attempt": 1},
            )
        except ProviderError as exc:
            ended_at = utc_now_iso()
            latency_ms = int((time.monotonic() - t0) * 1000)
            with deps.session_factory() as db:
                record_node_metric(
                    db,
                    run_id=run_id,
                    node="single_agent_run",
                    attempt=1,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=latency_ms,
                    provider=deps.llm.provider_name,
                    model=_node_model(adv.get("model_override") or deps.model, deps.llm.provider_name),
                    status="failed",
                    error_code=exc.code,
                )
                db.commit()
            return {
                "errors": [
                    *state.get("errors", []),
                    {"code": exc.code, "message": exc.message, "node": "single_agent_run"},
                ],
                "terminal_reason": exc.code,
                "next_route": "safe_stop",
                "updated_at": ended_at,
            }

        ended_at = utc_now_iso()
        latency_ms = int((time.monotonic() - t0) * 1000)
        draft_dict = res.output.draft.model_dump()
        ed_dict = {
            "score": res.output.self_editor_score,
            "score_breakdown": res.output.self_editor_breakdown.model_dump(),
            "verdict": "approve"
            if res.output.self_editor_score >= deps.limits.editor_approval_threshold
            else "revise",
            "critical_issues": [],
            "major_issues": [],
            "minor_issues": [],
            "rewrite_instructions": [],
            "summary": res.output.self_editor_summary,
        }
        fc_dict = res.output.fact_check.model_dump()
        llm_res = res.llm_result
        cost = calculate_node_cost(
            provider=llm_res.provider,
            model=llm_res.model,
            prompt_tokens=llm_res.prompt_tokens,
            completion_tokens=llm_res.completion_tokens,
        )

        with deps.session_factory() as db:
            art = create_artifact_version(
                db,
                run_id=run_id,
                title=res.output.draft.title,
                hook=res.output.draft.hook,
                body_markdown=res.output.draft.body_markdown,
                platform=state["normalized_brief"]["platform"],
                outline=res.output.draft.outline,
                thread_segments=res.output.draft.thread_segments,
                created_by="single_agent",
                status="draft",
                parent_version_id=state.get("latest_artifact_id"),
                is_agent_approved=False,
            )
            persist_claims_ledger(
                db,
                run_id=run_id,
                artifact_id=art.id,
                claims=fc_dict.get("claims", []),
            )
            record_node_metric(
                db,
                run_id=run_id,
                node="single_agent_run",
                attempt=1,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                model_latency_ms=llm_res.latency_ms,
                provider=llm_res.provider,
                model=llm_res.model,
                input_tokens=llm_res.prompt_tokens,
                output_tokens=llm_res.completion_tokens,
                total_tokens=llm_res.total_tokens,
                cost_dict=cost.to_dict(),
                prompt_version=res.prompt_version,
                status="completed",
            )
            db.commit()
            art_id = art.id

        _save_run_progress(
            deps,
            run_id,
            current_node="single_agent_run",
            checkpoint_key="step_single_agent",
            state_snapshot={"self_score": ed_dict["score"]},
            fields={"editor_result_json": ed_dict, "fact_check_result_json": fc_dict},
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="single_agent_run",
            message=f"Single-agent baseline draft completed (self-score {ed_dict['score']}/100).",
        )
        return {
            "draft": draft_dict,
            "latest_artifact_id": art_id,
            "editor_result": ed_dict,
            "fact_check_result": fc_dict,
            "next_route": "finalizer",
            "current_node": "single_agent_run",
            "updated_at": ended_at,
            "total_step_count": state.get("total_step_count", 0) + 1,
        }

    async def finalizer(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        started_at = utc_now_iso()
        if _is_cancelled(deps, run_id):
            return {"cancelled": True, "terminal_reason": "RUN_CANCELLED", "updated_at": started_at}

        draft = state.get("draft") or {}
        sources = state.get("sources") or []
        fc = state.get("fact_check_result") or {}
        warnings = list(state.get("warnings") or [])

        uncertain_cnt = int(fc.get("uncertain_count") or 0)
        partial_claims = [
            c for c in (fc.get("claims") or []) if c.get("status") == "partially_supported"
        ]
        if uncertain_cnt > 0 or partial_claims:
            warnings.append(
                {
                    "code": "CLAIM_QUALIFIED",
                    "message": (
                        f"{uncertain_cnt + len(partial_claims)} claim(s) remain uncertain or partially supported and require human review."
                    ),
                    "node": "finalizer",
                }
            )
        if state.get("fact_remediation_count", 0) > 0:
            warnings.append(
                {
                    "code": "CLAIM_REMEDIATED",
                    "message": "One or more claims were revised or qualified during fact-check remediation.",
                    "node": "finalizer",
                }
            )

        non_demo_warnings = [w for w in warnings if w.get("code") != "DEMO_MODE"]
        final_status = "completed_with_warnings" if non_demo_warnings else "completed"
        formatted_body = _format_final_markdown(draft=draft, sources=sources, warnings=warnings)

        with deps.session_factory() as db:
            art = create_artifact_version(
                db,
                run_id=run_id,
                title=str(draft.get("title") or state["normalized_brief"]["topic"][:100]),
                hook=draft.get("hook"),
                body_markdown=formatted_body,
                platform=state["normalized_brief"]["platform"],
                outline=draft.get("outline") or [],
                thread_segments=draft.get("thread_segments") or [],
                created_by="finalizer",
                status="approved",
                parent_version_id=state.get("latest_artifact_id"),
                is_agent_approved=True,
            )
            if fc.get("claims"):
                persist_claims_ledger(
                    db,
                    run_id=run_id,
                    artifact_id=art.id,
                    claims=fc.get("claims", []),
                )
            record_node_metric(
                db,
                run_id=run_id,
                node="finalizer",
                attempt=1,
                started_at=started_at,
                ended_at=utc_now_iso(),
                latency_ms=2,
                status="completed",
            )
            db.commit()
            art_id = art.id
            art_ver = art.version

        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="node.completed",
            status="completed",
            node="finalizer",
            message=f"Finalized artifact version {art_ver} ready for review and export.",
            safe_payload={"artifact_id": art_id, "version": art_ver, "final_status": final_status},
        )
        return {
            "status": final_status,
            "final_artifact": {"artifact_id": art_id, "version": art_ver},
            "latest_artifact_id": art_id,
            "warnings": warnings,
            "current_node": "finalizer",
            "updated_at": utc_now_iso(),
            "terminal_reason": final_status.upper(),
        }

    async def safe_stop(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        now = utc_now_iso()
        cancelled = bool(state.get("cancelled")) or _is_cancelled(deps, run_id)
        reason = "RUN_CANCELLED" if cancelled else (state.get("terminal_reason") or "SAFE_STOP")
        final_status = "cancelled" if cancelled else "failed"

        draft = state.get("draft")
        latest_art_id = state.get("latest_artifact_id")
        if draft and draft.get("body_markdown"):
            with deps.session_factory() as db:
                art = create_artifact_version(
                    db,
                    run_id=run_id,
                    title=str(draft.get("title") or state["normalized_brief"]["topic"][:100]),
                    hook=draft.get("hook"),
                    body_markdown=str(draft["body_markdown"]),
                    platform=state["normalized_brief"]["platform"],
                    outline=draft.get("outline") or [],
                    thread_segments=draft.get("thread_segments") or [],
                    created_by="safe_stop",
                    status="partial",
                    parent_version_id=latest_art_id,
                    is_agent_approved=False,
                )
                db.commit()
                latest_art_id = art.id

        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type="run.warning" if not cancelled else "node.completed",
            status=final_status,
            node="safe_stop",
            message=f"Workflow terminated safely ({reason}).",
            safe_payload={"terminal_reason": reason, "partial_preserved": bool(draft)},
        )
        return {
            "status": final_status,
            "cancelled": cancelled,
            "latest_artifact_id": latest_art_id,
            "terminal_reason": reason,
            "current_node": "safe_stop",
            "updated_at": now,
        }

    async def persist_result(state: VeridraState) -> dict[str, Any]:
        run_id = state["run_id"]
        attempt_id = state.get("attempt_id", "att_1")
        finished_at = utc_now_iso()
        final_status = state.get("status") or "failed"
        if final_status not in TERMINAL_STATUSES:
            final_status = "failed"

        with deps.session_factory() as db:
            run = db.get(Run, run_id)
            if run is not None and run.status not in TERMINAL_STATUSES:
                duration_ms: int | None = None
                if run.started_at:
                    try:
                        from datetime import datetime

                        st = datetime.fromisoformat(run.started_at.replace("Z", "+00:00"))
                        en = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                        duration_ms = max(0, int((en - st).total_seconds() * 1000))
                    except Exception:
                        duration_ms = None

                run.warnings_json = state.get("warnings") or []
                run.errors_json = state.get("errors") or []
                run.editor_revision_count = state.get(
                    "editor_revision_count", run.editor_revision_count
                )
                run.fact_remediation_count = state.get(
                    "fact_remediation_count", run.fact_remediation_count
                )
                run.research_retry_count = state.get(
                    "research_retry_count", run.research_retry_count
                )
                run.total_step_count = state.get("total_step_count", run.total_step_count)
                run.finished_at = finished_at
                run.duration_ms = duration_ms
                update_run_status_safe(
                    db,
                    run,
                    new_status=final_status,
                    current_node=state.get("current_node") or "persist_result",
                    terminal_reason=state.get("terminal_reason"),
                )
                save_checkpoint_snapshot(
                    db,
                    run_id=run_id,
                    checkpoint_key="step_terminal",
                    state_snapshot={
                        "status": final_status,
                        "terminal_reason": state.get("terminal_reason"),
                    },
                )
                db.commit()

        evt_type = (
            "run.cancelled"
            if final_status == "cancelled"
            else ("run.failed" if final_status == "failed" else "run.completed")
        )
        await _emit(
            deps,
            run_id=run_id,
            attempt_id=attempt_id,
            event_type=evt_type,
            status=final_status,
            node="persist_result",
            message=f"Run finished with status '{final_status}'.",
            safe_payload={
                "status": final_status,
                "terminal_reason": state.get("terminal_reason"),
            },
        )
        cancellation_registry.clear(run_id)
        return {"status": final_status, "updated_at": finished_at}

    return {
        "initialize_run": initialize_run,
        "plan_research": plan_research,
        "researcher": researcher,
        "evidence_gate": evidence_gate,
        "writer": writer,
        "editor": editor,
        "editor_router": editor_router,
        "fact_checker": fact_checker,
        "fact_router": fact_router,
        "single_agent_run": single_agent_run,
        "finalizer": finalizer,
        "safe_stop": safe_stop,
        "persist_result": persist_result,
    }
