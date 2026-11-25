import asyncio
import math
import statistics
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import BenchmarkCase, BenchmarkExperiment, Run
from app.evaluation.dataset import DATASET_BY_ID, EVALUATION_DATASET_V1, BenchmarkTopic
from app.providers.factory import resolve_providers
from app.schemas.api import (
    AdvancedWorkflowOptions,
    BenchmarkCaseRead,
    BenchmarkConditionSummary,
    BenchmarkCreateRequest,
    BenchmarkDetailRead,
    ContentRequest,
)
from app.schemas.common import new_id, utc_now_iso
from app.services.run_persistence import build_run_summary
from app.workers.runner import create_run_record, execute_run


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct
    low = math.floor(idx)
    high = math.ceil(idx)
    if low == high:
        return float(ordered[int(idx)])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (idx - low))


def select_topics(req: BenchmarkCreateRequest) -> list[BenchmarkTopic]:
    if req.topic_ids:
        chosen = [DATASET_BY_ID[tid] for tid in req.topic_ids if tid in DATASET_BY_ID]
        if chosen:
            return chosen
    pool = [t for t in EVALUATION_DATASET_V1 if req.include_holdout or not t.is_holdout]
    return pool[: req.topic_count]


def create_benchmark_experiment(
    db: Session,
    *,
    req: BenchmarkCreateRequest,
    execution_mode: str,
) -> BenchmarkExperiment:
    topics = select_topics(req)
    exp_id = new_id("bmk")
    now = utc_now_iso()

    limitations = [
        f"Sample size: {len(topics)} topic(s) x {req.repeats} repeat(s) across {len(req.strategies)} condition(s).",
        "Automated editorial scores and claim counts measure rubric alignment and traceability, not independent human truth.",
    ]
    if execution_mode == "demo":
        limitations.append(
            "DEMO MODE: Results were produced by deterministic mock adapters, not live Gemini or Tavily calls."
        )
    if len(topics) < 15:
        limitations.append(
            "Small cohort size; do not overclaim statistical significance without larger paired runs and blind human evaluation."
        )

    exp = BenchmarkExperiment(
        id=exp_id,
        name=req.name.strip(),
        dataset_version=req.dataset_version,
        execution_mode=execution_mode,
        config_json={
            "topic_ids": [t.topic_id for t in topics],
            "strategies": req.strategies,
            "repeats": req.repeats,
            "include_holdout": req.include_holdout,
            "model_override": req.model_override,
            "provider_override": req.provider_override,
        },
        status="queued",
        limitations_json=limitations,
        created_at=now,
    )
    db.add(exp)
    db.flush()

    for topic in topics:
        for strategy in req.strategies:
            for rep in range(1, req.repeats + 1):
                db.add(
                    BenchmarkCase(
                        id=new_id("bmc"),
                        experiment_id=exp_id,
                        topic_id=topic.topic_id,
                        condition=strategy,
                        repeat_index=rep,
                        run_id=None,
                        evaluator_json={},
                        created_at=now,
                    )
                )
    db.commit()
    db.refresh(exp)
    return exp


async def execute_benchmark_experiment(
    experiment_id: str,
    *,
    session_factory: Any,
    use_demo_mode: bool = False,
) -> None:
    """Execute all paired benchmark cases under controlled identical topic inputs."""
    settings = get_settings()
    with session_factory() as db:
        exp = db.get(BenchmarkExperiment, experiment_id)
        if exp is None:
            return
        exp.status = "running"
        db.commit()
        cases = db.scalars(
            select(BenchmarkCase)
            .where(BenchmarkCase.experiment_id == experiment_id)
            .order_by(BenchmarkCase.topic_id.asc(), BenchmarkCase.repeat_index.asc())
        ).all()
        case_specs = [(c.id, c.topic_id, c.condition) for c in cases]
        exec_mode = exp.execution_mode
        model_override = (exp.config_json or {}).get("model_override")
        provider_override = (exp.config_json or {}).get("provider_override")

    for case_id, topic_id, condition in case_specs:
        topic = DATASET_BY_ID.get(topic_id)
        if topic is None:
            continue
        is_demo = use_demo_mode or (exec_mode == "demo") or settings.demo_mode
        bundle = resolve_providers(
            use_demo_mode=is_demo,
            mock_scenario=topic.mock_scenario if is_demo else None,
            model_override=model_override,
            provider_override=provider_override,
            settings=settings,
        )
        req = ContentRequest(
            topic=topic.topic,
            goal=topic.goal,
            platform=topic.platform,
            audience=topic.audience,
            depth=topic.depth,
            required_points=topic.required_points,
            prohibited_points=topic.prohibited_points,
            workflow_strategy=condition,  # type: ignore[arg-type]
            use_demo_mode=is_demo,
            advanced=AdvancedWorkflowOptions(
                model_override=model_override,
                provider_override=provider_override,
                temperature=0.1,
                mock_scenario=topic.mock_scenario if is_demo else None,
            ),
        )
        with session_factory() as db:
            run = create_run_record(
                db,
                req=req,
                execution_mode=bundle.execution_mode,
                initial_warnings=bundle.warnings,
            )
            case_row = db.get(BenchmarkCase, case_id)
            if case_row is not None:
                case_row.run_id = run.id
                db.commit()
            run_id = run.id

        await execute_run(run_id, provider_bundle=bundle)

    with session_factory() as db:
        exp = db.get(BenchmarkExperiment, experiment_id)
        if exp is not None:
            exp.status = "completed"
            exp.finished_at = utc_now_iso()
            db.commit()


def launch_benchmark_background(
    experiment_id: str,
    *,
    session_factory: Any,
    use_demo_mode: bool = False,
) -> asyncio.Task[None]:
    return asyncio.create_task(
        execute_benchmark_experiment(
            experiment_id,
            session_factory=session_factory,
            use_demo_mode=use_demo_mode,
        ),
        name=f"veridra-benchmark-{experiment_id}",
    )


def build_benchmark_detail(db: Session, exp: BenchmarkExperiment) -> BenchmarkDetailRead:
    case_rows = db.scalars(
        select(BenchmarkCase)
        .where(BenchmarkCase.experiment_id == exp.id)
        .order_by(
            BenchmarkCase.topic_id.asc(),
            BenchmarkCase.condition.asc(),
            BenchmarkCase.repeat_index.asc(),
        )
    ).all()

    cases_out: list[BenchmarkCaseRead] = []
    cases_by_cond: dict[str, list[BenchmarkCaseRead]] = {}

    for c in case_rows:
        topic_obj = DATASET_BY_ID.get(c.topic_id)
        run = db.get(Run, c.run_id) if c.run_id else None
        summary = build_run_summary(db, run) if run is not None else None
        claims_count = 0
        unsupported_rate: float | None = None
        contradiction_rate: float | None = None
        revision_count = 0

        if run is not None:
            revision_count = run.editor_revision_count + run.fact_remediation_count
            fc = run.fact_check_result_json or {}
            claims = [x for x in (fc.get("claims") or []) if x.get("status") != "not_checked"]
            claims_count = len(claims)
            if claims_count > 0:
                unsup = sum(1 for x in claims if x.get("status") in {"unsupported", "uncertain"})
                contra = sum(1 for x in claims if x.get("status") == "contradicted")
                unsupported_rate = round(unsup / claims_count, 4)
                contradiction_rate = round(contra / claims_count, 4)

        eval_data = c.evaluator_json or {}
        case_item = BenchmarkCaseRead(
            case_id=c.id,
            topic_id=c.topic_id,
            topic=topic_obj.topic if topic_obj else c.topic_id,
            category=topic_obj.category if topic_obj else "general",
            risk_profile=topic_obj.risk_profile if topic_obj else "standard",
            condition=c.condition,  # type: ignore[arg-type]
            repeat_index=c.repeat_index,
            run_id=c.run_id,
            status=summary.status if summary else "queued",
            editor_score=summary.editor_score if summary else None,
            evidence_coverage=summary.evidence_coverage if summary else None,
            unsupported_claim_rate=unsupported_rate,
            contradiction_rate=contradiction_rate,
            duration_ms=summary.duration_ms if summary else None,
            total_tokens=summary.total_tokens if summary else None,
            estimated_cost=summary.estimated_cost if summary else None,
            cost_status=summary.cost_status if summary else "unavailable",
            revision_count=revision_count,
            human_rating=eval_data.get("human_rating"),
            human_notes=eval_data.get("human_notes"),
        )
        cases_out.append(case_item)
        cases_by_cond.setdefault(c.condition, []).append(case_item)

    summaries: list[BenchmarkConditionSummary] = []
    for cond, items in cases_by_cond.items():
        n = len(items)
        completed_items = [i for i in items if i.status in {"completed", "completed_with_warnings"}]
        failed_items = [i for i in items if i.status == "failed"]
        scores = [float(i.editor_score) for i in items if i.editor_score is not None]
        covs = [i.evidence_coverage for i in items if i.evidence_coverage is not None]
        unsup_rates = [
            i.unsupported_claim_rate for i in items if i.unsupported_claim_rate is not None
        ]
        contra_rates = [i.contradiction_rate for i in items if i.contradiction_rate is not None]
        durations = [float(i.duration_ms) for i in items if i.duration_ms is not None]
        tokens = [i.total_tokens for i in items if i.total_tokens is not None]
        costs = [i.estimated_cost for i in items if i.estimated_cost is not None]
        human_ratings = [i.human_rating for i in items if i.human_rating is not None]

        tot_cost = round(sum(costs), 8) if costs else None
        cost_per_accepted = (
            round(tot_cost / len(completed_items), 8)
            if (tot_cost is not None and completed_items)
            else None
        )
        summaries.append(
            BenchmarkConditionSummary(
                condition=cond,  # type: ignore[arg-type]
                sample_size=n,
                completed_count=len(completed_items),
                failed_count=len(failed_items),
                error_rate=round(len(failed_items) / n, 4) if n else 0.0,
                avg_editor_score=round(statistics.mean(scores), 2) if scores else None,
                median_editor_score=round(statistics.median(scores), 2) if scores else None,
                avg_evidence_coverage=round(statistics.mean(covs), 4) if covs else None,
                avg_unsupported_rate=round(statistics.mean(unsup_rates), 4)
                if unsup_rates
                else None,
                avg_contradiction_rate=round(statistics.mean(contra_rates), 4)
                if contra_rates
                else None,
                median_duration_ms=round(_percentile(durations, 0.5) or 0.0, 1)
                if durations
                else None,
                p90_duration_ms=round(_percentile(durations, 0.9) or 0.0, 1) if durations else None,
                total_tokens=sum(tokens) if tokens else None,
                total_estimated_cost=tot_cost,
                cost_per_accepted_artifact=cost_per_accepted,
                cost_status="measured_estimated" if tot_cost is not None else "unavailable",
                avg_human_rating=round(statistics.mean(human_ratings), 2)
                if human_ratings
                else None,
                human_rating_count=len(human_ratings),
            )
        )

    return BenchmarkDetailRead(
        benchmark_id=exp.id,
        name=exp.name,
        dataset_version=exp.dataset_version,
        status=exp.status,
        execution_mode=exp.execution_mode,
        config=exp.config_json or {},
        condition_summaries=summaries,
        cases=cases_out,
        limitations=exp.limitations_json or [],
        created_at=exp.created_at,
        finished_at=exp.finished_at,
    )
