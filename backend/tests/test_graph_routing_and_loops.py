import pytest
from sqlalchemy import select

from app.db.models import Artifact, Run
from app.db.session import get_session_factory
from app.providers.factory import ProviderBundle
from app.providers.mock import MockLLMProvider, MockSearchProvider
from app.schemas.api import ContentRequest
from app.services.event_bus import cancellation_registry
from app.services.run_persistence import build_run_detail, update_run_status_safe
from app.workers.runner import create_run_record, execute_run


async def _run_scenario(
    *,
    scenario: str,
    topic: str = "How ICPC develops algorithmic problem-solving skills",
    search_available: bool = True,
    source_urls: list[str] | None = None,
) -> tuple[str, object]:
    session_factory = get_session_factory()
    req = ContentRequest(
        topic=topic,
        platform="linkedin",
        source_urls=source_urls or [],
        use_demo_mode=True,
    )
    bundle = ProviderBundle(
        llm=MockLLMProvider(scenario=scenario),
        search=MockSearchProvider(scenario=scenario) if search_available else None,
        execution_mode="demo",
        warnings=(
            []
            if search_available
            else [
                {
                    "code": "SEARCH_UNAVAILABLE",
                    "message": "Search unavailable",
                    "node": "researcher",
                }
            ]
        ),
    )
    with session_factory() as db:
        run = create_run_record(
            db,
            req=req,
            execution_mode="demo",
            initial_warnings=bundle.warnings,
        )
        run_id = run.id

    await execute_run(run_id, provider_bundle=bundle)
    with session_factory() as db:
        r = db.get(Run, run_id)
        assert r is not None
        detail = build_run_detail(db, r)
    return run_id, detail


@pytest.mark.asyncio
async def test_graph_happy_path() -> None:
    _, detail = await _run_scenario(scenario="happy_path")
    assert detail.status == "completed"
    assert detail.quality.editor_score == 89
    assert detail.quality.fact_status == "pass"
    assert detail.metrics.editor_revision_count == 0
    assert detail.metrics.fact_remediation_count == 0
    assert len(detail.sources) >= 2
    assert len(detail.claims) >= 1
    assert detail.latest_artifact is not None
    assert detail.latest_artifact.status == "approved"
    assert "## Sources" in detail.latest_artifact.body_markdown


@pytest.mark.asyncio
async def test_graph_editor_revision_loop_and_approval() -> None:
    _, detail = await _run_scenario(scenario="editor_revision")
    assert detail.status == "completed"
    assert detail.metrics.editor_revision_count == 1
    assert detail.quality.editor_score == 89
    # Writer v1 + Writer v2 + Finalizer v3
    assert len(detail.artifacts) == 3


@pytest.mark.asyncio
async def test_graph_editor_loop_stops_at_max_revisions() -> None:
    _, detail = await _run_scenario(scenario="editor_max_revisions")
    assert detail.status == "failed"
    assert detail.metrics.editor_revision_count == 3
    assert detail.terminal_reason == "RETRY_LIMIT_REACHED"
    assert detail.latest_artifact is not None
    assert detail.latest_artifact.status == "partial"


@pytest.mark.asyncio
async def test_graph_research_gate_retries_once_then_stops_safely() -> None:
    _, detail = await _run_scenario(scenario="insufficient_evidence")
    assert detail.status == "failed"
    assert detail.metrics.research_retry_count == 1
    assert detail.terminal_reason == "INSUFFICIENT_EVIDENCE"
    assert detail.latest_artifact is None


@pytest.mark.asyncio
async def test_graph_fact_remediation_loop_corrects_claim() -> None:
    _, detail = await _run_scenario(scenario="fact_remediation")
    assert detail.status == "completed_with_warnings"
    assert detail.metrics.fact_remediation_count == 1
    assert detail.quality.fact_status == "pass"
    assert any(w.code == "CLAIM_REMEDIATED" for w in detail.warnings)


@pytest.mark.asyncio
async def test_graph_fact_remediation_stops_at_cap_on_contradiction() -> None:
    _, detail = await _run_scenario(scenario="contradiction_stop")
    assert detail.status == "failed"
    assert detail.metrics.fact_remediation_count == 2
    assert detail.terminal_reason == "RETRY_LIMIT_REACHED"
    assert detail.quality.contradicted_claims >= 1
    assert detail.latest_artifact is not None
    assert detail.latest_artifact.status == "partial"


@pytest.mark.asyncio
async def test_graph_uncertain_claim_proceeds_only_with_warning() -> None:
    _, detail = await _run_scenario(scenario="uncertain_claim")
    assert detail.status == "completed_with_warnings"
    assert detail.quality.uncertain_claims >= 1
    assert any(w.code == "CLAIM_QUALIFIED" for w in detail.warnings)


@pytest.mark.asyncio
async def test_graph_provider_failure_marks_run_failed_safely() -> None:
    _, detail = await _run_scenario(scenario="provider_rate_limit")
    assert detail.status == "failed"
    assert detail.terminal_reason == "PROVIDER_RATE_LIMIT"
    assert any(ev.event_type == "run.failed" for ev in detail.events)


@pytest.mark.asyncio
async def test_graph_cancellation_stops_execution_and_terminal_status_immutable() -> None:
    session_factory = get_session_factory()
    req = ContentRequest(topic="ICPC cancellation test", platform="linkedin", use_demo_mode=True)
    bundle = ProviderBundle(
        llm=MockLLMProvider(scenario="happy_path"),
        search=MockSearchProvider(scenario="happy_path"),
        execution_mode="demo",
        warnings=[],
    )
    with session_factory() as db:
        run = create_run_record(db, req=req, execution_mode="demo", initial_warnings=[])
        run_id = run.id

    cancellation_registry.request_cancel(run_id)
    await execute_run(run_id, provider_bundle=bundle)

    with session_factory() as db:
        r = db.get(Run, run_id)
        assert r is not None
        assert r.status == "cancelled"
        # Terminal status cannot be overwritten back to running
        changed = update_run_status_safe(db, r, new_status="running")
        assert changed is False
        assert r.status == "cancelled"
        arts = db.scalars(select(Artifact).where(Artifact.run_id == run_id)).all()
        assert arts == []


@pytest.mark.asyncio
async def test_graph_fact_remediation_stops_at_max_attempts_on_unsupported() -> None:
    _, detail = await _run_scenario(scenario="fact_max_remediations")
    assert detail.status == "failed"
    assert detail.metrics.fact_remediation_count == 2
    assert detail.terminal_reason == "RETRY_LIMIT_REACHED"
    assert detail.quality.unsupported_claims >= 1
    assert detail.latest_artifact is not None
    assert detail.latest_artifact.status == "partial"


@pytest.mark.asyncio
async def test_graph_search_unavailable_uses_user_supplied_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.providers.base import PageResult

    async def fake_fetch(url: str) -> PageResult:
        return PageResult(
            original_url=url,
            canonical_url=url,
            title="User Supplied ICPC Doc",
            text_excerpt="ICPC teams of three solve algorithmic problems on one machine.",
            publisher="icpc.global",
            published_at=None,
            fetched_at="2026-11-25T10:00:00Z",
            content_type="text/html",
            status="retrieved",
        )

    monkeypatch.setattr("app.agents.researcher.safe_fetch_public_page", fake_fetch)
    _, detail = await _run_scenario(
        scenario="happy_path",
        search_available=False,
        source_urls=["https://icpc.global/worldfinals/rules"],
    )
    assert detail.status == "completed_with_warnings"
    assert any(w.code == "SEARCH_UNAVAILABLE" for w in detail.warnings)
    assert len(detail.sources) == 1
    assert detail.sources[0].source_type == "user_supplied"
