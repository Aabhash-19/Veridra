from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.pricing import RATE_CARD_VERSION
from app.db.models import (
    Artifact,
    Checkpoint,
    Claim,
    ClaimEvidence,
    EvidenceItem,
    NodeMetric,
    Run,
    RunEvent,
    Source,
)
from app.schemas.api import (
    ArtifactSummaryRead,
    ClaimRecordRead,
    DraftArtifactRead,
    EvidenceItemRead,
    NodeMetricRead,
    NormalizedBrief,
    RunDetailRead,
    RunEventRead,
    RunMetricsSummary,
    RunQualitySummary,
    RunSummaryRead,
    RunWarning,
    SourceRecordRead,
)
from app.schemas.common import new_id, utc_now_iso

TERMINAL_STATUSES = {"completed", "completed_with_warnings", "failed", "cancelled"}


def append_run_event(
    db: Session,
    *,
    run_id: str,
    event_type: str,
    status: str,
    message: str,
    node: str | None = None,
    attempt_id: str = "att_1",
    safe_payload: dict[str, Any] | None = None,
    sequence: int | None = None,
) -> RunEventRead:
    """Append an ordered, idempotent event to run_events."""
    if sequence is None:
        max_seq = db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id))
        sequence = (max_seq or 0) + 1

    existing = db.scalar(
        select(RunEvent).where(
            RunEvent.run_id == run_id,
            RunEvent.attempt_id == attempt_id,
            RunEvent.node == node,
            RunEvent.sequence == sequence,
        )
    )
    if existing is not None:
        return RunEventRead(
            event_id=existing.id,
            run_id=existing.run_id,
            sequence=existing.sequence,
            node=existing.node,
            event_type=existing.event_type,
            status=existing.status,
            message=existing.message,
            safe_payload=existing.payload_json or {},
            created_at=existing.created_at,
        )

    evt = RunEvent(
        id=new_id("evt"),
        run_id=run_id,
        attempt_id=attempt_id,
        sequence=sequence,
        node=node,
        event_type=event_type,
        status=status,
        message=message,
        payload_json=safe_payload or {},
        created_at=utc_now_iso(),
    )
    db.add(evt)
    db.flush()
    return RunEventRead(
        event_id=evt.id,
        run_id=evt.run_id,
        sequence=evt.sequence,
        node=evt.node,
        event_type=evt.event_type,
        status=evt.status,
        message=evt.message,
        safe_payload=evt.payload_json or {},
        created_at=evt.created_at,
    )


def save_checkpoint_snapshot(
    db: Session,
    *,
    run_id: str,
    checkpoint_key: str,
    state_snapshot: dict[str, Any],
) -> None:
    """Persist a JSON checkpoint snapshot into the checkpoints table."""
    existing = db.scalar(
        select(Checkpoint).where(
            Checkpoint.run_id == run_id,
            Checkpoint.checkpoint_key == checkpoint_key,
        )
    )
    now = utc_now_iso()
    if existing is not None:
        existing.state_json = state_snapshot
        existing.created_at = now
    else:
        db.add(
            Checkpoint(
                id=new_id("chk"),
                run_id=run_id,
                checkpoint_key=checkpoint_key,
                state_json=state_snapshot,
                created_at=now,
            )
        )
    db.flush()


def persist_sources_and_evidence(
    db: Session,
    *,
    run_id: str,
    sources: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
) -> None:
    """Upsert deduplicated Source and EvidenceItem records for a run."""
    source_db_id_by_key: dict[str, str] = {}
    existing_sources = db.scalars(select(Source).where(Source.run_id == run_id)).all()
    existing_by_key = {s.source_key: s for s in existing_sources}

    for src in sources:
        s_key = str(src["source_id"])
        meta = {
            "snippet": src.get("snippet", ""),
            "fetched_text_excerpt": src.get("fetched_text_excerpt"),
            "credibility_score": src.get("credibility_score"),
            "relevance_score": src.get("relevance_score"),
            "source_type": src.get("source_type", "web"),
            "fetch_error": src.get("fetch_error"),
        }
        if s_key in existing_by_key:
            row = existing_by_key[s_key]
            row.status = str(src.get("status", row.status))
            row.metadata_json = meta
            source_db_id_by_key[s_key] = row.id
        else:
            row = Source(
                id=new_id("src"),
                run_id=run_id,
                source_key=s_key,
                url=str(src["url"]),
                canonical_url=str(src.get("canonical_url") or src["url"]),
                title=str(src.get("title") or src["url"])[:500],
                publisher=str(src.get("publisher") or "unknown")[:255],
                published_at=src.get("published_at"),
                accessed_at=str(src.get("accessed_at") or utc_now_iso()),
                status=str(src.get("status") or "retrieved"),
                metadata_json=meta,
                created_at=utc_now_iso(),
            )
            db.add(row)
            db.flush()
            source_db_id_by_key[s_key] = row.id

    existing_ev = db.scalars(select(EvidenceItem).where(EvidenceItem.run_id == run_id)).all()
    existing_ev_by_key = {e.evidence_key: e for e in existing_ev}

    for ev in evidence_items:
        e_key = str(ev["evidence_id"])
        s_key = str(ev["source_id"])
        src_db_id = source_db_id_by_key.get(s_key)
        if not src_db_id:
            continue
        meta = {
            "confidence": ev.get("confidence"),
            "created_by_node": ev.get("created_by_node", "researcher"),
            "related_claim_ids": ev.get("related_claim_ids", []),
        }
        if e_key in existing_ev_by_key:
            row_ev = existing_ev_by_key[e_key]
            row_ev.excerpt = str(ev["quote_or_paraphrase"])
            row_ev.role = str(ev.get("support_type") or "supports")
            row_ev.metadata_json = meta
        else:
            db.add(
                EvidenceItem(
                    id=new_id("ev"),
                    run_id=run_id,
                    evidence_key=e_key,
                    source_id=src_db_id,
                    excerpt=str(ev["quote_or_paraphrase"]),
                    role=str(ev.get("support_type") or "supports"),
                    location_hint=ev.get("location_hint"),
                    metadata_json=meta,
                    created_at=utc_now_iso(),
                )
            )
    db.flush()


def create_artifact_version(
    db: Session,
    *,
    run_id: str,
    title: str,
    hook: str | None,
    body_markdown: str,
    platform: str,
    outline: list[str],
    thread_segments: list[str],
    created_by: str,
    status: str,
    parent_version_id: str | None = None,
    is_agent_approved: bool = False,
) -> Artifact:
    """Create a new immutable Artifact version with strictly incrementing version number."""
    max_ver = db.scalar(select(func.max(Artifact.version)).where(Artifact.run_id == run_id))
    next_ver = (max_ver or 0) + 1
    if parent_version_id is None and next_ver > 1:
        prev = db.scalar(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.version == next_ver - 1)
        )
        if prev is not None:
            parent_version_id = prev.id

    words = len([w for w in body_markdown.split() if w.strip()])
    art = Artifact(
        id=new_id("art"),
        run_id=run_id,
        version=next_ver,
        parent_version_id=parent_version_id,
        title=title[:300],
        hook=hook,
        body_markdown=body_markdown,
        platform=platform,
        outline_json=outline,
        thread_segments_json=thread_segments,
        word_count=words,
        char_count=len(body_markdown),
        created_by=created_by,
        status=status,
        is_agent_approved=is_agent_approved,
        created_at=utc_now_iso(),
    )
    db.add(art)
    db.flush()
    return art


def persist_claims_ledger(
    db: Session,
    *,
    run_id: str,
    artifact_id: str | None,
    claims: list[dict[str, Any]],
) -> None:
    """Persist evaluated claims and many-to-many claim_evidence links."""
    existing_claims = db.scalars(select(Claim).where(Claim.run_id == run_id)).all()
    for old_claim in existing_claims:
        db.delete(old_claim)
    db.flush()

    ev_rows = db.scalars(select(EvidenceItem).where(EvidenceItem.run_id == run_id)).all()
    ev_db_by_key = {e.evidence_key: e.id for e in ev_rows}

    for item in claims:
        c_key = str(item["claim_id"])
        claim_row = Claim(
            id=new_id("cl"),
            run_id=run_id,
            artifact_id=artifact_id,
            claim_key=c_key,
            claim_text=str(item["claim_text"]),
            claim_type=str(item.get("claim_type") or "factual"),
            status=str(item["status"]),
            confidence=item.get("confidence"),
            explanation=str(item["explanation"]),
            materiality=str(item.get("materiality") or "medium"),
            recommended_action=str(item.get("recommended_action") or "keep"),
            created_at=utc_now_iso(),
        )
        db.add(claim_row)
        db.flush()

        for ev_key in item.get("supporting_evidence_ids") or []:
            ev_db_id = ev_db_by_key.get(str(ev_key))
            if ev_db_id:
                db.add(
                    ClaimEvidence(
                        claim_id=claim_row.id,
                        evidence_id=ev_db_id,
                        relationship="supports",
                    )
                )
        for ev_key in item.get("contradicting_evidence_ids") or []:
            ev_db_id = ev_db_by_key.get(str(ev_key))
            if ev_db_id:
                db.add(
                    ClaimEvidence(
                        claim_id=claim_row.id,
                        evidence_id=ev_db_id,
                        relationship="contradicts",
                    )
                )
    db.flush()


def record_node_metric(
    db: Session,
    *,
    run_id: str,
    node: str,
    attempt: int,
    started_at: str,
    ended_at: str,
    latency_ms: int,
    model_latency_ms: int | None = None,
    tool_latency_ms: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_dict: dict[str, Any] | None = None,
    tool_calls: int = 0,
    prompt_version: str | None = None,
    status: str = "completed",
    error_code: str | None = None,
) -> None:
    """Persist per-node telemetry into node_metrics."""
    usage_json = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    db.add(
        NodeMetric(
            id=new_id("met"),
            run_id=run_id,
            node=node,
            attempt=attempt,
            started_at=started_at,
            ended_at=ended_at,
            provider=provider,
            model=model,
            usage_json=usage_json,
            latency_ms=latency_ms,
            model_latency_ms=model_latency_ms,
            tool_latency_ms=tool_latency_ms,
            cost_json=cost_dict or {"estimated_cost": None, "cost_status": "unavailable"},
            tool_calls=tool_calls,
            prompt_version=prompt_version,
            status=status,
            error_code=error_code,
            created_at=utc_now_iso(),
        )
    )
    db.flush()


def update_run_status_safe(
    db: Session,
    run: Run,
    *,
    new_status: str,
    current_node: str | None = None,
    terminal_reason: str | None = None,
) -> bool:
    """Enforce invariant: terminal run statuses cannot transition back to running or be overwritten."""
    if run.status in TERMINAL_STATUSES:
        return False
    run.status = new_status
    if current_node is not None:
        run.current_node = current_node
    if terminal_reason is not None:
        run.terminal_reason = terminal_reason
    run.updated_at = utc_now_iso()
    db.flush()
    return True


def _build_sources_and_evidence_read(
    db: Session, run_id: str
) -> tuple[list[SourceRecordRead], list[EvidenceItemRead]]:
    source_rows = db.scalars(
        select(Source).where(Source.run_id == run_id).order_by(Source.created_at.asc())
    ).all()
    ev_rows = db.scalars(
        select(EvidenceItem)
        .where(EvidenceItem.run_id == run_id)
        .order_by(EvidenceItem.created_at.asc())
    ).all()
    claim_rows = db.scalars(select(Claim).where(Claim.run_id == run_id)).all()
    ce_rows = (
        db.scalars(
            select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([c.id for c in claim_rows]))
        ).all()
        if claim_rows
        else []
    )

    claim_key_by_db_id = {c.id: c.claim_key for c in claim_rows}
    related_claims_by_ev: dict[str, list[str]] = {}
    for ce in ce_rows:
        ck = claim_key_by_db_id.get(ce.claim_id)
        if ck:
            related_claims_by_ev.setdefault(ce.evidence_id, []).append(ck)

    src_by_db_id = {s.id: s for s in source_rows}
    sources_out = [
        SourceRecordRead(
            source_id=s.source_key,
            url=s.url,
            canonical_url=s.canonical_url,
            title=s.title,
            publisher=s.publisher,
            published_at=s.published_at,
            accessed_at=s.accessed_at,
            snippet=(s.metadata_json or {}).get("snippet", ""),
            fetched_text_excerpt=(s.metadata_json or {}).get("fetched_text_excerpt"),
            credibility_score=(s.metadata_json or {}).get("credibility_score"),
            relevance_score=(s.metadata_json or {}).get("relevance_score"),
            source_type=(s.metadata_json or {}).get("source_type", "web"),
            status=s.status,  # type: ignore[arg-type]
            fetch_error=(s.metadata_json or {}).get("fetch_error"),
        )
        for s in source_rows
    ]
    evidence_out = [
        EvidenceItemRead(
            evidence_id=e.evidence_key,
            source_id=src_by_db_id[e.source_id].source_key if e.source_id in src_by_db_id else "",
            source_url=src_by_db_id[e.source_id].url if e.source_id in src_by_db_id else None,
            source_title=src_by_db_id[e.source_id].title if e.source_id in src_by_db_id else None,
            quote_or_paraphrase=e.excerpt,
            location_hint=e.location_hint,
            related_claim_ids=related_claims_by_ev.get(e.id, []),
            support_type=e.role,  # type: ignore[arg-type]
            confidence=(e.metadata_json or {}).get("confidence"),
            created_by_node=(e.metadata_json or {}).get("created_by_node", "researcher"),
        )
        for e in ev_rows
    ]
    return sources_out, evidence_out


def build_claims_read(db: Session, run_id: str) -> list[ClaimRecordRead]:
    claim_rows = db.scalars(
        select(Claim).where(Claim.run_id == run_id).order_by(Claim.created_at.asc())
    ).all()
    if not claim_rows:
        return []
    ev_rows = db.scalars(select(EvidenceItem).where(EvidenceItem.run_id == run_id)).all()
    ev_key_by_db_id = {e.id: e.evidence_key for e in ev_rows}
    ce_rows = db.scalars(
        select(ClaimEvidence).where(ClaimEvidence.claim_id.in_([c.id for c in claim_rows]))
    ).all()

    sup_map: dict[str, list[str]] = {}
    con_map: dict[str, list[str]] = {}
    for ce in ce_rows:
        ekey = ev_key_by_db_id.get(ce.evidence_id)
        if not ekey:
            continue
        if ce.relationship == "supports":
            sup_map.setdefault(ce.claim_id, []).append(ekey)
        elif ce.relationship == "contradicts":
            con_map.setdefault(ce.claim_id, []).append(ekey)

    return [
        ClaimRecordRead(
            claim_id=c.claim_key,
            claim_text=c.claim_text,
            claim_type=c.claim_type,
            materiality=c.materiality,  # type: ignore[arg-type]
            status=c.status,  # type: ignore[arg-type]
            confidence=c.confidence,
            supporting_evidence_ids=sup_map.get(c.id, []),
            contradicting_evidence_ids=con_map.get(c.id, []),
            explanation=c.explanation,
            recommended_action=c.recommended_action,  # type: ignore[arg-type]
        )
        for c in claim_rows
    ]


def aggregate_run_metrics(run: Run, metric_rows: Sequence[NodeMetric]) -> RunMetricsSummary:
    llm_rows = [m for m in metric_rows if m.provider is not None]
    reported_in: list[int] = [
        int(val)
        for m in llm_rows
        if isinstance((val := (m.usage_json or {}).get("input_tokens")), int)
    ]
    reported_out: list[int] = [
        int(val)
        for m in llm_rows
        if isinstance((val := (m.usage_json or {}).get("output_tokens")), int)
    ]
    reported_tot: list[int] = [
        int(val)
        for m in llm_rows
        if isinstance((val := (m.usage_json or {}).get("total_tokens")), int)
    ]

    if not llm_rows or not reported_tot:
        tok_status = "unavailable"
    elif len(reported_tot) == len(llm_rows):
        tok_status = "measured"
    else:
        tok_status = "partial"

    costs: list[float] = [
        float(val)
        for m in llm_rows
        if isinstance((val := (m.cost_json or {}).get("estimated_cost")), int | float)
    ]
    if not llm_rows or not costs:
        cost_status = "unavailable"
        est_cost = None
    elif len(costs) == len(llm_rows):
        cost_status = "measured_estimated"
        est_cost = round(sum(costs), 8)
    else:
        cost_status = "partial"
        est_cost = round(sum(costs), 8)

    currency = next(
        (
            (m.cost_json or {}).get("currency")
            for m in llm_rows
            if (m.cost_json or {}).get("currency")
        ),
        None,
    )

    return RunMetricsSummary(
        duration_ms=run.duration_ms,
        total_input_tokens=sum(reported_in) if reported_in else None,
        total_output_tokens=sum(reported_out) if reported_out else None,
        total_tokens=sum(reported_tot) if reported_tot else None,
        token_usage_status=tok_status,
        estimated_cost=est_cost,
        cost_status=cost_status,
        rate_card_version=RATE_CARD_VERSION if est_cost is not None else None,
        currency=currency,
        editor_revision_count=run.editor_revision_count,
        fact_remediation_count=run.fact_remediation_count,
        research_retry_count=run.research_retry_count,
        total_step_count=run.total_step_count,
    )


def compute_run_quality(run: Run, claims: list[ClaimRecordRead]) -> RunQualitySummary:
    ed = run.editor_result_json or {}
    fc = run.fact_check_result_json or {}
    material = [c for c in claims if c.status != "not_checked"]
    supported = sum(1 for c in material if c.status == "supported")
    partially = sum(1 for c in material if c.status == "partially_supported")
    unsupported = sum(1 for c in material if c.status == "unsupported")
    contradicted = sum(1 for c in material if c.status == "contradicted")
    uncertain = sum(1 for c in material if c.status == "uncertain")

    coverage = fc.get("evidence_coverage")
    if coverage is None and material:
        coverage = round((supported + partially) / len(material), 4)

    return RunQualitySummary(
        editor_score=ed.get("score"),
        editor_verdict=ed.get("verdict"),
        fact_status=fc.get("overall_status"),
        total_material_claims=len(material),
        supported_claims=supported,
        partially_supported_claims=partially,
        unsupported_claims=unsupported,
        contradicted_claims=contradicted,
        uncertain_claims=uncertain,
        evidence_coverage=coverage,
        warning_count=len(run.warnings_json or []),
    )


def build_artifact_detail(db: Session, art: Artifact) -> DraftArtifactRead:
    all_arts = db.scalars(
        select(Artifact).where(Artifact.run_id == art.run_id).order_by(Artifact.version.desc())
    ).all()
    approved_art = next((a for a in all_arts if a.is_agent_approved), None)
    differs = bool(
        approved_art is not None
        and (art.id != approved_art.id and art.body_markdown != approved_art.body_markdown)
    )
    sources, evidence = _build_sources_and_evidence_read(db, art.run_id)
    claims = build_claims_read(db, art.run_id)
    return DraftArtifactRead(
        artifact_id=art.id,
        run_id=art.run_id,
        version=art.version,
        parent_version_id=art.parent_version_id,
        title=art.title,
        hook=art.hook,
        body_markdown=art.body_markdown,
        platform=art.platform,  # type: ignore[arg-type]
        outline=art.outline_json or [],
        thread_segments=art.thread_segments_json or [],
        word_count=art.word_count,
        char_count=art.char_count,
        created_at=art.created_at,
        created_by=art.created_by,
        status=art.status,  # type: ignore[arg-type]
        differs_from_agent_approved=differs,
        claims=claims,
        sources=sources,
        evidence_items=evidence,
    )


def build_run_summary(db: Session, run: Run) -> RunSummaryRead:
    metric_rows = db.scalars(select(NodeMetric).where(NodeMetric.run_id == run.id)).all()
    claims = build_claims_read(db, run.id)
    quality = compute_run_quality(run, claims)
    metrics = aggregate_run_metrics(run, metric_rows)
    return RunSummaryRead(
        run_id=run.id,
        project_id=run.project_id,
        parent_run_id=run.parent_run_id,
        status=run.status,  # type: ignore[arg-type]
        execution_mode=run.execution_mode,
        workflow_strategy=run.workflow_strategy,  # type: ignore[arg-type]
        topic=run.topic,
        platform=run.platform,  # type: ignore[arg-type]
        current_node=run.current_node,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=run.duration_ms,
        editor_score=quality.editor_score,
        fact_status=quality.fact_status,
        evidence_coverage=quality.evidence_coverage,
        total_tokens=metrics.total_tokens,
        estimated_cost=metrics.estimated_cost,
        cost_status=metrics.cost_status,
        warning_count=quality.warning_count,
        terminal_reason=run.terminal_reason,
    )


def build_run_detail(db: Session, run: Run) -> RunDetailRead:
    sources, evidence = _build_sources_and_evidence_read(db, run.id)
    claims = build_claims_read(db, run.id)
    artifact_rows = db.scalars(
        select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.version.asc())
    ).all()
    approved_art = next((a for a in reversed(artifact_rows) if a.is_agent_approved), None)

    artifacts_summary = [
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
        for a in artifact_rows
    ]
    latest_art = build_artifact_detail(db, artifact_rows[-1]) if artifact_rows else None

    metric_rows = db.scalars(
        select(NodeMetric).where(NodeMetric.run_id == run.id).order_by(NodeMetric.created_at.asc())
    ).all()
    node_metrics_out = [
        NodeMetricRead(
            metric_id=m.id,
            node_name=m.node,
            attempt=m.attempt,
            started_at=m.started_at,
            ended_at=m.ended_at,
            duration_ms=m.latency_ms,
            model_latency_ms=m.model_latency_ms,
            tool_latency_ms=m.tool_latency_ms,
            provider=m.provider,
            model=m.model,
            input_tokens=(m.usage_json or {}).get("input_tokens"),
            output_tokens=(m.usage_json or {}).get("output_tokens"),
            total_tokens=(m.usage_json or {}).get("total_tokens"),
            estimated_cost=(m.cost_json or {}).get("estimated_cost"),
            cost_status=(m.cost_json or {}).get("cost_status", "unavailable"),
            rate_card_version=(m.cost_json or {}).get("rate_card_version"),
            currency=(m.cost_json or {}).get("currency"),
            tool_calls=m.tool_calls,
            prompt_version=m.prompt_version,
            status=m.status,
            error_code=m.error_code,
        )
        for m in metric_rows
    ]

    event_rows = db.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.sequence.asc())
    ).all()
    events_out = [
        RunEventRead(
            event_id=ev.id,
            run_id=ev.run_id,
            sequence=ev.sequence,
            node=ev.node,
            event_type=ev.event_type,
            status=ev.status,
            message=ev.message,
            safe_payload=ev.payload_json or {},
            created_at=ev.created_at,
        )
        for ev in event_rows
    ]

    quality = compute_run_quality(run, claims)
    metrics_summary = aggregate_run_metrics(run, metric_rows)
    norm_brief = (
        NormalizedBrief.model_validate(run.normalized_brief_json)
        if run.normalized_brief_json
        else None
    )
    warnings_out = [
        RunWarning(
            code=str(w.get("code", "WARNING")),
            message=str(w.get("message", "")),
            node=w.get("node"),
        )
        for w in (run.warnings_json or [])
    ]

    return RunDetailRead(
        run_id=run.id,
        project_id=run.project_id,
        parent_run_id=run.parent_run_id,
        status=run.status,  # type: ignore[arg-type]
        execution_mode=run.execution_mode,
        workflow_strategy=run.workflow_strategy,  # type: ignore[arg-type]
        platform=run.platform,  # type: ignore[arg-type]
        current_node=run.current_node,
        request=run.request_json,
        normalized_brief=norm_brief,
        research_brief=run.research_brief_json,
        editor_result=run.editor_result_json,
        fact_check_result=run.fact_check_result_json,
        warnings=warnings_out,
        errors=run.errors_json or [],
        prompt_versions=run.prompt_versions_json or {},
        quality=quality,
        metrics=metrics_summary,
        node_metrics=node_metrics_out,
        sources=sources,
        evidence_items=evidence,
        claims=claims,
        artifacts=artifacts_summary,
        latest_artifact=latest_art,
        events=events_out,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        terminal_reason=run.terminal_reason,
    )
