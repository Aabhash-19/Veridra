import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.errors import ApiError
from app.db.models import Artifact, Project, Run, RunEvent
from app.db.session import get_db, get_session_factory
from app.providers.base import ProviderError
from app.providers.factory import resolve_providers
from app.schemas.api import (
    ArtifactSummaryRead,
    ContentRequest,
    RunCancelResponse,
    RunCreateResponse,
    RunDetailRead,
    RunEventRead,
    RunListResponse,
    RunRetryResponse,
)
from app.schemas.common import utc_now_iso
from app.services.event_bus import cancellation_registry, event_bus
from app.services.run_persistence import (
    TERMINAL_STATUSES,
    append_run_event,
    build_run_detail,
    build_run_summary,
    update_run_status_safe,
)
from app.workers.runner import create_run_record, launch_run_background

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunCreateResponse, status_code=201)
async def create_run(
    payload: ContentRequest,
    db: Session = Depends(get_db),
) -> RunCreateResponse:
    if payload.project_id:
        proj = db.get(Project, payload.project_id)
        if proj is None:
            raise ApiError(
                status_code=404,
                code="INVALID_REQUEST",
                message=f"Project '{payload.project_id}' does not exist.",
            )

    try:
        bundle = resolve_providers(
            use_demo_mode=payload.use_demo_mode,
            mock_scenario=payload.advanced.mock_scenario,
            model_override=payload.advanced.model_override,
            provider_override=payload.advanced.provider_override,
        )
    except ProviderError as exc:
        raise ApiError(status_code=422, code=exc.code, message=exc.message) from exc

    run = create_run_record(
        db,
        req=payload,
        execution_mode=bundle.execution_mode,
        initial_warnings=bundle.warnings,
    )
    launch_run_background(run.id, provider_bundle=bundle)
    return RunCreateResponse(
        run_id=run.id,
        status=run.status,  # type: ignore[arg-type]
        execution_mode=run.execution_mode,
        events_url=f"/api/v1/runs/{run.id}/events",
    )


@router.get("", response_model=RunListResponse)
def list_runs(
    status: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> RunListResponse:
    filters = []
    if status:
        filters.append(Run.status == status)
    if platform:
        filters.append(Run.platform == platform)
    if project_id:
        filters.append(Run.project_id == project_id)
    if date_from:
        filters.append(Run.created_at >= date_from)
    if date_to:
        filters.append(Run.created_at <= date_to)
    if search and search.strip():
        filters.append(Run.topic.ilike(f"%{search.strip()}%"))

    count_stmt = select(func.count(Run.id))
    list_stmt = select(Run)
    for f in filters:
        count_stmt = count_stmt.where(f)
        list_stmt = list_stmt.where(f)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(list_stmt.order_by(Run.created_at.desc()).offset(offset).limit(limit)).all()

    return RunListResponse(
        items=[build_run_summary(db, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=RunDetailRead)
def get_run_detail(run_id: str, db: Session = Depends(get_db)) -> RunDetailRead:
    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Run '{run_id}' was not found.",
        )
    return build_run_detail(db, run)


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: str, db: Session = Depends(get_db)) -> None:
    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Run '{run_id}' was not found.",
        )
    cancellation_registry.request_cancel(run_id)
    db.delete(run)
    db.commit()


@router.post("/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(run_id: str, db: Session = Depends(get_db)) -> RunCancelResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Run '{run_id}' was not found.",
        )

    if run.status in TERMINAL_STATUSES:
        return RunCancelResponse(
            run_id=run.id,
            status=run.status,  # type: ignore[arg-type]
            cancellation_accepted=False,
            message=f"Run already reached terminal status '{run.status}'.",
        )

    cancellation_registry.request_cancel(run_id)
    run.cancel_requested = True

    if run.status == "queued":
        run.finished_at = utc_now_iso()
        update_run_status_safe(
            db,
            run,
            new_status="cancelled",
            terminal_reason="RUN_CANCELLED",
        )
        evt = append_run_event(
            db,
            run_id=run.id,
            event_type="run.cancelled",
            status="cancelled",
            node=run.current_node,
            message="Queued run cancelled before execution.",
            safe_payload={"terminal_reason": "RUN_CANCELLED"},
        )
        db.commit()
        await event_bus.publish(run.id, evt.model_dump())
        return RunCancelResponse(
            run_id=run.id,
            status="cancelled",
            cancellation_accepted=True,
            message="Queued run cancelled.",
        )

    db.commit()
    return RunCancelResponse(
        run_id=run.id,
        status=run.status,  # type: ignore[arg-type]
        cancellation_accepted=True,
        message="Cancellation requested; graph will stop cleanly at next safe boundary.",
    )


@router.post("/{run_id}/retry", response_model=RunRetryResponse, status_code=201)
async def retry_run(run_id: str, db: Session = Depends(get_db)) -> RunRetryResponse:
    original = db.get(Run, run_id)
    if original is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Run '{run_id}' was not found.",
        )

    req = ContentRequest.model_validate(original.request_json)
    try:
        bundle = resolve_providers(
            use_demo_mode=(original.execution_mode == "demo") or req.use_demo_mode,
            mock_scenario=req.advanced.mock_scenario,
            model_override=req.advanced.model_override,
            provider_override=req.advanced.provider_override,
        )
    except ProviderError as exc:
        raise ApiError(status_code=422, code=exc.code, message=exc.message) from exc

    child_run = create_run_record(
        db,
        req=req,
        execution_mode=bundle.execution_mode,
        initial_warnings=bundle.warnings,
        parent_run_id=original.id,
    )
    launch_run_background(child_run.id, provider_bundle=bundle)
    return RunRetryResponse(
        run_id=child_run.id,
        parent_run_id=original.id,
        status=child_run.status,  # type: ignore[arg-type]
        execution_mode=child_run.execution_mode,
        events_url=f"/api/v1/runs/{child_run.id}/events",
    )


@router.get("/{run_id}/artifacts", response_model=list[ArtifactSummaryRead])
def list_run_artifacts(run_id: str, db: Session = Depends(get_db)) -> list[ArtifactSummaryRead]:
    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Run '{run_id}' was not found.",
        )
    rows = db.scalars(
        select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.version.asc())
    ).all()
    approved_art = next((a for a in reversed(rows) if a.is_agent_approved), None)
    return [
        ArtifactSummaryRead(
            artifact_id=a.id,
            version=a.version,
            parent_version_id=a.parent_version_id,
            title=a.title,
            platform=a.platform,  # type: ignore[arg-type]
            word_count=a.word_count,
            char_count=a.char_count,
            created_at=a.created_at,
            created_by=a.created_by,
            status=a.status,  # type: ignore[arg-type]
            differs_from_agent_approved=bool(
                approved_art is not None
                and a.id != approved_art.id
                and a.body_markdown != approved_art.body_markdown
            ),
        )
        for a in rows
    ]


def _format_sse_event(payload: dict) -> str:
    seq = payload.get("sequence", 0)
    return f"id: {seq}\nevent: agent.progress\ndata: {json.dumps(payload)}\n\n"


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    after_sequence: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Run '{run_id}' was not found.",
        )

    last_seq = 0
    if after_sequence is not None:
        last_seq = after_sequence
    elif last_event_id and last_event_id.isdigit():
        last_seq = int(last_event_id)

    session_factory = get_session_factory()

    async def event_generator() -> AsyncIterator[str]:
        nonlocal last_seq
        queue = event_bus.subscribe(run_id)
        try:
            # 1. Replay persisted historical events newer than last_seq
            with session_factory() as replay_db:
                historical = replay_db.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.sequence > last_seq)
                    .order_by(RunEvent.sequence.asc())
                ).all()
                run_row = replay_db.get(Run, run_id)
                is_terminal_now = bool(run_row and run_row.status in TERMINAL_STATUSES)

            for row in historical:
                payload = RunEventRead(
                    event_id=row.id,
                    run_id=row.run_id,
                    sequence=row.sequence,
                    node=row.node,
                    event_type=row.event_type,
                    status=row.status,
                    message=row.message,
                    safe_payload=row.payload_json or {},
                    created_at=row.created_at,
                ).model_dump()
                last_seq = max(last_seq, row.sequence)
                yield _format_sse_event(payload)

            if is_terminal_now:
                return

            # 2. Stream live events with periodic heartbeat comments until terminal event
            while True:
                if await request.is_disconnected():
                    break
                try:
                    live_payload = await asyncio.wait_for(queue.get(), timeout=12.0)
                    seq = int(live_payload.get("sequence") or 0)
                    if seq <= last_seq:
                        continue
                    last_seq = seq
                    yield _format_sse_event(live_payload)
                    evt_type = live_payload.get("event_type")
                    evt_status = live_payload.get("status")
                    if evt_type in {"run.completed", "run.failed", "run.cancelled"} or (
                        evt_status in TERMINAL_STATUSES
                        and live_payload.get("node") == "persist_result"
                    ):
                        break
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    with session_factory() as check_db:
                        r = check_db.get(Run, run_id)
                        if r is None or r.status in TERMINAL_STATUSES:
                            # Flush any missed final events before closing
                            missed = check_db.scalars(
                                select(RunEvent)
                                .where(RunEvent.run_id == run_id, RunEvent.sequence > last_seq)
                                .order_by(RunEvent.sequence.asc())
                            ).all()
                            for row in missed:
                                payload = RunEventRead(
                                    event_id=row.id,
                                    run_id=row.run_id,
                                    sequence=row.sequence,
                                    node=row.node,
                                    event_type=row.event_type,
                                    status=row.status,
                                    message=row.message,
                                    safe_payload=row.payload_json or {},
                                    created_at=row.created_at,
                                ).model_dump()
                                last_seq = max(last_seq, row.sequence)
                                yield _format_sse_event(payload)
                            break
        finally:
            event_bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
