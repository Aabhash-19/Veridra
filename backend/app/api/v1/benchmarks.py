from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.errors import ApiError
from app.core.config import get_settings
from app.db.models import BenchmarkCase, BenchmarkExperiment
from app.db.session import get_db, get_session_factory
from app.evaluation.benchmark_service import (
    build_benchmark_detail,
    create_benchmark_experiment,
    launch_benchmark_background,
)
from app.evaluation.dataset import EVALUATION_DATASET_V1
from app.providers.base import ProviderError
from app.providers.factory import resolve_providers
from app.schemas.api import (
    BenchmarkCaseRead,
    BenchmarkCreateRequest,
    BenchmarkDetailRead,
    BenchmarkListResponse,
    BenchmarkRatingRequest,
    BenchmarkTopicRead,
)

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("/dataset", response_model=list[BenchmarkTopicRead])
def list_evaluation_dataset() -> list[BenchmarkTopicRead]:
    return [
        BenchmarkTopicRead(
            topic_id=t.topic_id,
            category=t.category,
            risk_profile=t.risk_profile,
            topic=t.topic,
            goal=t.goal,
            platform=t.platform,
            audience=t.audience,
            depth=t.depth,
            expected_risk_notes=t.expected_risk_notes,
            is_holdout=t.is_holdout,
        )
        for t in EVALUATION_DATASET_V1
    ]


@router.post("", response_model=BenchmarkDetailRead, status_code=201)
async def create_benchmark(
    payload: BenchmarkCreateRequest,
    db: Session = Depends(get_db),
) -> BenchmarkDetailRead:
    settings = get_settings()
    try:
        bundle = resolve_providers(
            use_demo_mode=payload.use_demo_mode,
            model_override=payload.model_override,
            provider_override=payload.provider_override,
            settings=settings,
        )
    except ProviderError as exc:
        raise ApiError(status_code=422, code=exc.code, message=exc.message) from exc

    exp = create_benchmark_experiment(
        db,
        req=payload,
        execution_mode=bundle.execution_mode,
    )
    launch_benchmark_background(
        exp.id,
        session_factory=get_session_factory(),
        use_demo_mode=(bundle.execution_mode == "demo"),
    )
    return build_benchmark_detail(db, exp)


@router.get("", response_model=BenchmarkListResponse)
def list_benchmarks(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> BenchmarkListResponse:
    total = db.scalar(select(func.count(BenchmarkExperiment.id))) or 0
    rows = db.scalars(
        select(BenchmarkExperiment)
        .order_by(BenchmarkExperiment.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return BenchmarkListResponse(
        items=[build_benchmark_detail(db, exp) for exp in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{benchmark_id}", response_model=BenchmarkDetailRead)
def get_benchmark(benchmark_id: str, db: Session = Depends(get_db)) -> BenchmarkDetailRead:
    exp = db.get(BenchmarkExperiment, benchmark_id)
    if exp is None:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Benchmark '{benchmark_id}' was not found.",
        )
    return build_benchmark_detail(db, exp)


@router.post("/{benchmark_id}/cases/{case_id}/rating", response_model=BenchmarkCaseRead)
def submit_case_human_rating(
    benchmark_id: str,
    case_id: str,
    payload: BenchmarkRatingRequest,
    db: Session = Depends(get_db),
) -> BenchmarkCaseRead:
    case_row = db.get(BenchmarkCase, case_id)
    if case_row is None or case_row.experiment_id != benchmark_id:
        raise ApiError(
            status_code=404,
            code="INVALID_REQUEST",
            message=f"Benchmark case '{case_id}' was not found in experiment '{benchmark_id}'.",
        )
    ev_json = dict(case_row.evaluator_json or {})
    ev_json["human_rating"] = payload.rating
    ev_json["human_notes"] = payload.notes
    case_row.evaluator_json = ev_json
    db.commit()

    exp = db.get(BenchmarkExperiment, benchmark_id)
    assert exp is not None
    detail = build_benchmark_detail(db, exp)
    matched = next((c for c in detail.cases if c.case_id == case_id), None)
    assert matched is not None
    return matched
