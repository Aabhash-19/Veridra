import pytest
from pydantic import ValidationError

from app.core.logging import redact_sensitive
from app.core.pricing import calculate_node_cost
from app.core.security import UnsafeURLError, canonicalize_url, validate_url_syntax
from app.schemas.agents import EditorResult, FactCheckResult, ResearchBrief, WriterDraftOutput
from app.schemas.api import ContentRequest


def test_content_request_validation_rejects_invalid_inputs() -> None:
    # Blank / too short topic
    with pytest.raises(ValidationError):
        ContentRequest(topic="   hi   ", platform="linkedin")

    # Invalid platform
    with pytest.raises(ValidationError):
        ContentRequest(topic="Valid technical topic", platform="tiktok")  # type: ignore[arg-type]

    # Unsafe URL schemes
    for bad_url in [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hello",
        "http://127.0.0.1/admin",
        "http://localhost:8000/secret",
        "http://169.254.169.254/latest/meta-data/",
    ]:
        with pytest.raises(ValidationError):
            ContentRequest(topic="Valid technical topic", source_urls=[bad_url])

    # Oversized topic
    with pytest.raises(ValidationError):
        ContentRequest(topic="a" * 12500)

    # Valid URL passes and deduplicates
    req = ContentRequest(
        topic="ICPC problem solving habits",
        platform="linkedin",
        source_urls=[
            "https://icpc.global/worldfinals/rules",
            "https://icpc.global/worldfinals/rules",
        ],
    )
    assert len(req.source_urls) == 1


def test_url_syntax_and_canonicalization() -> None:
    with pytest.raises(UnsafeURLError):
        validate_url_syntax("https://user:pass@example.com/path")
    canon = canonicalize_url("HTTPS://Example.COM:443/article/?utm_source=x&id=2")
    assert canon == "https://example.com/article?id=2"


def test_agent_output_schemas_validate() -> None:
    rb = ResearchBrief.model_validate(
        {
            "research_summary": "Summary of retrieved public evidence.",
            "research_questions": ["Q1"],
            "key_findings": [{"finding": "Team of three", "evidence_ids": ["ev_1"]}],
            "sources": [
                {
                    "source_id": "src_1",
                    "url": "https://icpc.global/rules",
                    "title": "Rules",
                    "publisher": "icpc.global",
                    "published_at": None,
                    "accessed_at": "2026-11-25T10:00:00Z",
                    "relevance": 0.9,
                }
            ],
            "evidence_items": [
                {
                    "evidence_id": "ev_1",
                    "source_id": "src_1",
                    "excerpt": "Teams consist of three students.",
                    "supports": ["Team format"],
                }
            ],
            "open_questions": [],
            "confidence_notes": [],
        }
    )
    assert rb.sources[0].source_id == "src_1"

    wd = WriterDraftOutput.model_validate(
        {
            "title": "ICPC Insights",
            "hook": "Why algorithmic contests train careful debugging.",
            "body_markdown": "ICPC pairs three teammates on one machine to solve algorithmic tasks.",
            "outline": ["Hook", "Format", "Takeaway"],
            "factual_claims": [
                {
                    "claim_id": "cl_1",
                    "text": "Three students share one workstation.",
                    "evidence_ids": ["ev_1"],
                }
            ],
        }
    )
    assert wd.factual_claims[0].claim_id == "cl_1"

    ed = EditorResult.model_validate(
        {
            "score": 88,
            "score_breakdown": {
                "clarity": 18,
                "depth": 17,
                "audience": 14,
                "structure": 13,
                "platform_fit": 13,
                "specificity": 9,
                "tone": 4,
            },
            "verdict": "approve",
            "summary": "Clear and specific editorial structure.",
        }
    )
    assert ed.score_breakdown.computed_total == 88

    fc = FactCheckResult.model_validate(
        {
            "overall_status": "pass",
            "claims": [
                {
                    "claim_id": "cl_1",
                    "claim_text": "Three students share one workstation.",
                    "status": "supported",
                    "confidence": 0.9,
                    "supporting_evidence_ids": ["ev_1"],
                    "contradicting_evidence_ids": [],
                    "explanation": "Supported by official ICPC rules.",
                    "recommended_action": "keep",
                }
            ],
            "evidence_coverage": 1.0,
        }
    )
    assert fc.claims[0].status == "supported"


def test_cost_accounting_never_fabricates_missing_values() -> None:
    # Mock/demo always unavailable
    demo_cost = calculate_node_cost(
        provider="mock",
        model="gemini-2.5-flash",
        prompt_tokens=100,
        completion_tokens=50,
    )
    assert demo_cost.estimated_cost is None
    assert demo_cost.cost_status == "unavailable"

    # Missing usage fields
    missing_usage = calculate_node_cost(
        provider="gemini",
        model="gemini-2.5-flash",
        prompt_tokens=None,
        completion_tokens=120,
    )
    assert missing_usage.estimated_cost is None
    assert missing_usage.cost_status == "unavailable"

    # Unlisted model
    unknown_model = calculate_node_cost(
        provider="gemini",
        model="gemini-experimental-unknown",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert unknown_model.estimated_cost is None
    assert unknown_model.cost_status == "unavailable"

    # Valid listed model with full token counts
    measured = calculate_node_cost(
        provider="gemini",
        model="gemini-2.5-flash",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    )
    assert measured.estimated_cost == pytest.approx(0.75)
    assert measured.cost_status == "measured_estimated"
    assert measured.currency == "USD"


def test_log_secret_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("GEMINI_API_KEY", "secret-gemini-123456789")
    get_settings.cache_clear()
    cleaned = redact_sensitive(
        "Authorization: Bearer abc12345 url=https://api.test?api_key=xyz999 key=secret-gemini-123456789"
    )
    assert "secret-gemini-123456789" not in cleaned
    assert "abc12345" not in cleaned
    assert "xyz999" not in cleaned
    get_settings.cache_clear()
