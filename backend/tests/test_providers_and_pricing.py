import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from google.genai import errors as genai_errors

from app.agents.fact_checker import run_fact_checker_agent
from app.providers.base import ProviderError
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockLLMProvider
from app.providers.tavily import safe_fetch_public_page
from app.schemas.agents import EditorResult, ScoreBreakdown


@pytest.mark.asyncio
async def test_gemini_provider_success_and_missing_usage() -> None:
    provider = GeminiProvider(api_key="test-key-12345", max_retries=0)

    payload = EditorResult(
        score=88,
        score_breakdown=ScoreBreakdown(
            clarity=18, depth=17, audience=14, structure=13, platform_fit=13, specificity=9, tone=4
        ),
        verdict="approve",
        summary="Strong structure.",
    )

    # 1. Success with usage metadata
    fake_resp = SimpleNamespace(
        text=json.dumps(payload.model_dump()),
        usage_metadata=SimpleNamespace(
            prompt_token_count=120, candidates_token_count=45, total_token_count=165
        ),
        response_id="resp_1",
    )
    provider._client = MagicMock()
    provider._client.aio.models.generate_content = AsyncMock(return_value=fake_resp)

    res = await provider.generate_structured(
        model="gemini-2.5-flash",
        system_prompt="sys",
        user_payload={"draft": "hi"},
        response_schema=EditorResult,
        temperature=0.1,
        trace_context={"node": "editor"},
    )
    assert res.parsed.score == 88
    assert res.prompt_tokens == 120
    assert res.completion_tokens == 45
    assert res.total_tokens == 165

    # 2. Missing usage metadata stays None (never fabricated)
    no_usage_resp = SimpleNamespace(
        text=json.dumps(payload.model_dump()),
        usage_metadata=None,
        response_id="resp_2",
    )
    provider._client.aio.models.generate_content = AsyncMock(return_value=no_usage_resp)
    res2 = await provider.generate_structured(
        model="gemini-2.5-flash",
        system_prompt="sys",
        user_payload={"draft": "hi"},
        response_schema=EditorResult,
        temperature=0.1,
        trace_context={"node": "editor"},
    )
    assert res2.prompt_tokens is None
    assert res2.total_tokens is None


@pytest.mark.asyncio
async def test_gemini_provider_repair_and_failure_modes() -> None:
    provider = GeminiProvider(api_key="test-key-12345", max_retries=0)
    valid_payload = EditorResult(
        score=86,
        score_breakdown=ScoreBreakdown(
            clarity=17, depth=17, audience=14, structure=13, platform_fit=13, specificity=8, tone=4
        ),
        verdict="approve",
        summary="Repaired cleanly.",
    )

    # 1. Malformed JSON repaired on bounded single repair pass
    bad_resp = SimpleNamespace(text="{not valid json", usage_metadata=None, response_id="r1")
    repaired_resp = SimpleNamespace(
        text=json.dumps(valid_payload.model_dump()),
        usage_metadata=None,
        response_id="r2",
    )
    provider._client = MagicMock()
    provider._client.aio.models.generate_content = AsyncMock(side_effect=[bad_resp, repaired_resp])

    res = await provider.generate_structured(
        model="gemini-2.5-flash",
        system_prompt="sys",
        user_payload={"draft": "hi"},
        response_schema=EditorResult,
        temperature=0.1,
        trace_context={"node": "editor"},
    )
    assert res.parsed.score == 86
    assert provider._client.aio.models.generate_content.call_count == 2

    # 2. Malformed JSON twice -> PROVIDER_INVALID_OUTPUT
    provider._client.aio.models.generate_content = AsyncMock(side_effect=[bad_resp, bad_resp])
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate_structured(
            model="gemini-2.5-flash",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={"node": "editor"},
        )
    assert exc_info.value.code == "PROVIDER_INVALID_OUTPUT"

    # 3. Rate limit 429 -> PROVIDER_RATE_LIMIT
    err_429 = genai_errors.APIError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}}, None)
    provider._client.aio.models.generate_content = AsyncMock(side_effect=err_429)
    with pytest.raises(ProviderError) as exc_rate:
        await provider.generate_structured(
            model="gemini-2.5-flash",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={"node": "editor"},
        )
    assert exc_rate.value.code == "PROVIDER_RATE_LIMIT"

    # 4. Invalid API key 401 -> PROVIDER_NOT_CONFIGURED
    err_401 = genai_errors.APIError(401, {"error": {"message": "API_KEY_INVALID"}}, None)
    provider._client.aio.models.generate_content = AsyncMock(side_effect=err_401)
    with pytest.raises(ProviderError) as exc_key:
        await provider.generate_structured(
            model="gemini-2.5-flash",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={"node": "editor"},
        )
    assert exc_key.value.code == "PROVIDER_NOT_CONFIGURED"

    # 5. Timeout -> PROVIDER_TIMEOUT
    provider._client.aio.models.generate_content = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(ProviderError) as exc_to:
        await provider.generate_structured(
            model="gemini-3.6-flash",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={"node": "editor"},
        )
    assert exc_to.value.code == "PROVIDER_TIMEOUT"

    # 6. Retired/missing 404 model -> friendly PROVIDER_UNAVAILABLE
    err_404 = genai_errors.APIError(404, {"error": {"message": "NOT_FOUND"}}, None)
    provider._client.aio.models.generate_content = AsyncMock(side_effect=err_404)
    with pytest.raises(ProviderError) as exc_404:
        await provider.generate_structured(
            model="gemini-2.5-flash",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={"node": "editor"},
        )
    assert exc_404.value.code == "PROVIDER_UNAVAILABLE"
    assert "3.6 Flash" in exc_404.value.message

    # 7. High-demand 503 -> friendly retryable PROVIDER_UNAVAILABLE
    err_503 = genai_errors.APIError(503, {"error": {"message": "UNAVAILABLE"}}, None)
    provider._client.aio.models.generate_content = AsyncMock(side_effect=err_503)
    with pytest.raises(ProviderError) as exc_503:
        await provider.generate_structured(
            model="gemini-3.8-flash",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={"node": "editor"},
        )
    assert exc_503.value.code == "PROVIDER_UNAVAILABLE"
    assert exc_503.value.retryable is True

    # 8. Legacy retired model aliases upgrade cleanly
    from app.core.pricing import resolve_live_gemini_model

    assert resolve_live_gemini_model("gemini-2.5-flash") == "gemini-3.6-flash"
    assert resolve_live_gemini_model("gemini-2.0-flash") == "gemini-3.5-flash-lite"
    assert resolve_live_gemini_model("gemini-3.5-flash") == "gemini-3.5-flash"

    # 9. Gemini smart backup fails over from busy 503 model to working backup and records real model
    backup_provider = GeminiProvider(
        api_key="test-key-12345",
        max_retries=0,
        fallback_models=("gemini-3.5-flash",),
    )
    ok_resp = SimpleNamespace(
        text=json.dumps(valid_payload.model_dump()),
        usage_metadata=SimpleNamespace(
            prompt_token_count=90, candidates_token_count=30, total_token_count=120
        ),
        response_id="resp_failover",
    )
    backup_provider._client = MagicMock()
    backup_provider._client.aio.models.generate_content = AsyncMock(
        side_effect=[err_503, ok_resp]
    )
    failover_res = await backup_provider.generate_structured(
        model="gemini-3.6-flash",
        system_prompt="sys",
        user_payload={},
        response_schema=EditorResult,
        temperature=0.1,
        trace_context={"node": "editor"},
    )
    assert failover_res.model == "gemini-3.5-flash"
    assert failover_res.total_tokens == 120


@pytest.mark.asyncio
async def test_openai_compatible_and_anthropic_providers_and_routing() -> None:
    from app.core.config import Settings
    from app.providers.anthropic_provider import AnthropicProvider
    from app.providers.factory import resolve_providers
    from app.providers.openai_compat import OpenAICompatibleProvider

    valid_editor = EditorResult(
        score=91,
        score_breakdown=ScoreBreakdown(
            clarity=19, depth=18, audience=14, structure=14, platform_fit=13, specificity=9, tone=4
        ),
        verdict="approve",
        summary="Crisp ChatGPT draft.",
    )

    # 1. OpenAI-compatible: rejects response_format -> falls back cleanly -> succeeds with usage
    seen_calls: list[dict] = []

    def openai_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen_calls.append(body)
        if len(seen_calls) == 1:
            return httpx.Response(400, text="response_format json_object unsupported")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_1",
                "choices": [{"message": {"content": json.dumps(valid_editor.model_dump())}}],
                "usage": {"prompt_tokens": 110, "completion_tokens": 45, "total_tokens": 155},
            },
        )

    oa_provider = OpenAICompatibleProvider(
        provider_name="openai",
        api_key="sk-test-openai-12345",
        base_url="https://api.openai.com/v1",
        max_retries=0,
        transport=httpx.MockTransport(openai_handler),
    )
    oa_res = await oa_provider.generate_structured(
        model="gpt-4o-mini",
        system_prompt="Edit carefully.",
        user_payload={"draft": "hello"},
        response_schema=EditorResult,
        temperature=0.2,
        trace_context={"node": "editor"},
    )
    assert oa_res.provider == "openai"
    assert oa_res.model == "gpt-4o-mini"
    assert oa_res.parsed.score == 91
    assert oa_res.total_tokens == 155
    assert "response_format" not in seen_calls[1]

    # 2. Groq rate limit -> PROVIDER_RATE_LIMIT
    groq_429 = OpenAICompatibleProvider(
        provider_name="groq",
        api_key="gsk-test-12345",
        base_url="https://api.groq.com/openai/v1",
        max_retries=0,
        transport=httpx.MockTransport(lambda _r: httpx.Response(429, text="rate_limit")),
    )
    with pytest.raises(ProviderError) as exc_groq:
        await groq_429.generate_structured(
            model="llama-3.3-70b-versatile",
            system_prompt="sys",
            user_payload={},
            response_schema=EditorResult,
            temperature=0.1,
            trace_context={},
        )
    assert exc_groq.value.code == "PROVIDER_RATE_LIMIT"

    # 3. Anthropic structured tool_use output
    def anthropic_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "emit_structured_output",
                        "input": valid_editor.model_dump(),
                    }
                ],
                "usage": {"input_tokens": 80, "output_tokens": 40},
            },
        )

    anth_provider = AnthropicProvider(
        api_key="sk-ant-test-12345",
        max_retries=0,
        transport=httpx.MockTransport(anthropic_handler),
    )
    anth_res = await anth_provider.generate_structured(
        model="claude-3-5-haiku-latest",
        system_prompt="sys",
        user_payload={"draft": "hi"},
        response_schema=EditorResult,
        temperature=0.2,
        trace_context={},
    )
    assert anth_res.provider == "anthropic"
    assert anth_res.parsed.score == 91
    assert anth_res.total_tokens == 120

    # 4. Multi-provider factory routing & clear missing-key error
    cfg_openai = Settings(openai_api_key="sk-test-openai-999999", gemini_api_key="")
    bundle_oa = resolve_providers(model_override="gpt-4o-mini", settings=cfg_openai)
    assert bundle_oa.execution_mode == "live"
    assert bundle_oa.llm.provider_name == "openai"

    with pytest.raises(ProviderError) as exc_missing_claude:
        resolve_providers(model_override="claude-3-5-haiku-latest", settings=cfg_openai)
    assert exc_missing_claude.value.code == "PROVIDER_NOT_CONFIGURED"

    # 5. Cross-provider failover when primary hits 429 rate limit
    from app.providers.resilient import ResilientLLMProvider

    resilient = ResilientLLMProvider(
        primary_provider=groq_429,
        primary_model="openai/gpt-oss-120b",
        backups=[(oa_provider, "gpt-4o-mini")],
    )
    failover_res = await resilient.generate_structured(
        model="openai/gpt-oss-120b",
        system_prompt="Edit carefully.",
        user_payload={"draft": "hello"},
        response_schema=EditorResult,
        temperature=0.2,
        trace_context={"node": "editor"},
    )
    assert failover_res.provider == "openai"
    assert failover_res.model == "gpt-4o-mini"
    assert failover_res.parsed.score == 91


@pytest.mark.asyncio
async def test_safe_fetch_public_page_ssrf_and_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bypass live DNS resolution in unit test for mock transport public domain
    async def fake_ssrf_ok(url: str) -> str:
        from app.core.security import validate_url_syntax

        cleaned = validate_url_syntax(url)
        return cleaned

    monkeypatch.setattr("app.providers.tavily.validate_url_ssrf_safe", fake_ssrf_ok)

    # 1. Valid HTML extraction
    def handler_ok(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redirect-unsafe":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8080/internal"})
        if request.url.path == "/forbidden":
            return httpx.Response(403, text="Forbidden")
        if request.url.path == "/binary":
            return httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%PDF")
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html><head><title>ICPC Rules</title></head><body><p>Teams of three.</p><script>bad()</script></body></html>",
        )

    transport = httpx.MockTransport(handler_ok)
    ok_res = await safe_fetch_public_page("https://icpc.global/rules", transport=transport)
    assert ok_res.status == "retrieved"
    assert "Teams of three." in ok_res.text_excerpt
    assert "bad()" not in ok_res.text_excerpt

    # 2. Redirect to loopback blocked
    redir_res = await safe_fetch_public_page(
        "https://icpc.global/redirect-unsafe", transport=transport
    )
    assert redir_res.status == "inaccessible"
    assert redir_res.error_code == "UNSAFE_REDIRECT"

    # 3. 403 -> inaccessible
    forb_res = await safe_fetch_public_page("https://icpc.global/forbidden", transport=transport)
    assert forb_res.status == "inaccessible"

    # 4. Unsupported content-type
    bin_res = await safe_fetch_public_page("https://icpc.global/binary", transport=transport)
    assert bin_res.status == "unsupported_content_type"


@pytest.mark.asyncio
async def test_fact_checker_strips_hallucinated_evidence_ids() -> None:
    class HallucinatingLLM(MockLLMProvider):
        async def generate_structured(self, **kwargs):  # type: ignore[override]
            res = await super().generate_structured(**kwargs)
            # Inject an evidence ID that does not exist in run evidence_items
            res.parsed.claims[0].supporting_evidence_ids = ["ev_does_not_exist"]
            res.parsed.claims[0].status = "supported"
            return res

    res = await run_fact_checker_agent(
        normalized_brief={"topic": "ICPC", "platform": "linkedin"},
        draft={
            "factual_claims": [
                {
                    "claim_id": "cl_1",
                    "text": "Unproven claim.",
                    "evidence_ids": [],
                    "materiality": "high",
                }
            ]
        },
        sources=[
            {
                "source_id": "src_1",
                "url": "https://icpc.global",
                "title": "ICPC",
                "publisher": "icpc.global",
                "status": "retrieved",
            }
        ],
        evidence_items=[
            {"evidence_id": "ev_1", "source_id": "src_1", "quote_or_paraphrase": "Team of 3."}
        ],
        llm=HallucinatingLLM(),
        model="mock",
    )
    assert res.fact_check_result.claims[0].supporting_evidence_ids == []
    assert res.fact_check_result.claims[0].status == "unsupported"
    assert res.fact_check_result.unsupported_count == 1
