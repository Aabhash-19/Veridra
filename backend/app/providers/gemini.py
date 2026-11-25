import asyncio
import json
import random
import time
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.core.logging import get_logger, redact_sensitive
from app.providers.base import LLMProvider, LLMResult, ProviderError, strip_json_fences

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Google GenAI SDK adapter with structured output, bounded backoff, and backup failover."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 45.0,
        max_retries: int = 3,
        fallback_models: tuple[str, ...] = (),
    ) -> None:
        if not api_key or not api_key.strip():
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "Gemini API key is not configured.",
                retryable=False,
            )
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._fallback_models = tuple(fallback_models)
        self._client = genai.Client(api_key=self._api_key)
        self._beta_client: genai.Client | None = None

    def _client_for_model(self, model: str) -> Any:
        # Use v1beta only for preview/latest aliases when using the real GenAI client.
        if ("-preview" in model or model.endswith("-latest")) and isinstance(
            self._client, genai.Client
        ):
            if self._beta_client is None:
                self._beta_client = genai.Client(
                    api_key=self._api_key,
                    http_options=types.HttpOptions(api_version="v1beta"),
                )
            return self._beta_client
        return self._client

    async def _call_once(
        self,
        *,
        model: str,
        system_prompt: str,
        payload_text: str,
        response_schema: type[T],
        temperature: float,
    ) -> tuple[str, int | None, int | None, int | None, str | None]:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature,
        )
        client = self._client_for_model(model)
        attempt = 0
        while True:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=payload_text,
                        config=config,
                    ),
                    timeout=self._timeout_seconds,
                )
                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = getattr(usage, "prompt_token_count", None) if usage else None
                completion_tokens = (
                    getattr(usage, "candidates_token_count", None) if usage else None
                )
                total_tokens = getattr(usage, "total_token_count", None) if usage else None
                if total_tokens is None and (
                    prompt_tokens is not None and completion_tokens is not None
                ):
                    total_tokens = prompt_tokens + completion_tokens
                request_id = getattr(response, "response_id", None)
                text = response.text or ""
                return text, prompt_tokens, completion_tokens, total_tokens, request_id
            except TimeoutError as exc:
                if attempt < self._max_retries:
                    attempt += 1
                    await asyncio.sleep(min(4.0, (0.6 * (2**attempt)) + random.uniform(0.05, 0.3)))
                    continue
                raise ProviderError(
                    "PROVIDER_TIMEOUT",
                    "Gemini took too long to respond. Please try again or pick another AI.",
                    retryable=True,
                    cause=exc,
                ) from exc
            except genai_errors.APIError as exc:
                status_code = getattr(exc, "code", None)
                msg = str(exc)
                if status_code in (401, 403) or "API_KEY_INVALID" in msg:
                    raise ProviderError(
                        "PROVIDER_NOT_CONFIGURED",
                        "Gemini API key was rejected by Google.",
                        retryable=False,
                        cause=exc,
                    ) from exc
                if status_code == 404 or "NOT_FOUND" in msg:
                    raise ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        f"AI model '{model}' is not available right now. Please try Gemini 3.6 Flash or ChatGPT.",
                        retryable=False,
                        cause=exc,
                    ) from exc
                if status_code == 429 or "RESOURCE_EXHAUSTED" in msg:
                    if attempt < self._max_retries:
                        attempt += 1
                        await asyncio.sleep(
                            min(6.0, (0.8 * (2**attempt)) + random.uniform(0.1, 0.4))
                        )
                        continue
                    raise ProviderError(
                        "PROVIDER_RATE_LIMIT",
                        f"Your Gemini limit for '{model}' is full right now. Try ChatGPT/Groq or wait a moment.",
                        retryable=True,
                        cause=exc,
                    ) from exc
                if status_code is not None and status_code >= 500 and attempt < self._max_retries:
                    attempt += 1
                    await asyncio.sleep(min(5.0, (0.6 * (2**attempt)) + random.uniform(0.05, 0.25)))
                    continue
                if status_code == 503 or "UNAVAILABLE" in msg:
                    raise ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        f"Google's '{model}' is experiencing heavy traffic right now. Switch to ChatGPT/Groq or retry shortly.",
                        retryable=True,
                        cause=exc,
                    ) from exc
                safe_detail = redact_sensitive(msg)[:180]
                raise ProviderError(
                    "INTERNAL_ERROR",
                    f"Gemini API error ({status_code or 'unknown'}): {safe_detail}",
                    retryable=False,
                    cause=exc,
                ) from exc
            except (httpx.HTTPError, OSError) as exc:
                raise ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "Could not reach Gemini right now. Please check your network or try another AI.",
                    retryable=True,
                    cause=exc,
                ) from exc
            except Exception as exc:
                raise ProviderError(
                    "INTERNAL_ERROR",
                    "Unexpected error calling Gemini provider.",
                    retryable=False,
                    cause=exc,
                ) from exc

    async def _call_with_model_failover(
        self,
        *,
        model: str,
        system_prompt: str,
        payload_text: str,
        response_schema: type[T],
        temperature: float,
    ) -> tuple[str, str, int | None, int | None, int | None, str | None]:
        candidates = [model] + [m for m in self._fallback_models if m != model]
        last_err: ProviderError | None = None
        for idx, cand in enumerate(candidates):
            try:
                text, p_tok, c_tok, t_tok, req_id = await self._call_once(
                    model=cand,
                    system_prompt=system_prompt,
                    payload_text=payload_text,
                    response_schema=response_schema,
                    temperature=temperature,
                )
                return cand, text, p_tok, c_tok, t_tok, req_id
            except ProviderError as exc:
                last_err = exc
                if exc.code in {"PROVIDER_UNAVAILABLE", "PROVIDER_RATE_LIMIT"} and idx + 1 < len(
                    candidates
                ):
                    logger.warning(
                        "Gemini model unavailable; failing over to backup Gemini model.",
                        extra={"extra_data": {"failed_model": cand, "next_model": candidates[idx + 1]}},
                    )
                    continue
                raise
        assert last_err is not None
        raise last_err

    async def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_schema: type[T],
        temperature: float,
        trace_context: dict[str, Any],
    ) -> LLMResult[T]:
        start_mono = time.monotonic()
        payload_text = json.dumps(user_payload, ensure_ascii=False)
        active_model, raw_text, p_tok, c_tok, t_tok, req_id = await self._call_with_model_failover(
            model=model,
            system_prompt=system_prompt,
            payload_text=payload_text,
            response_schema=response_schema,
            temperature=temperature,
        )

        cleaned = strip_json_fences(raw_text)
        try:
            parsed = response_schema.model_validate_json(cleaned)
            latency_ms = int((time.monotonic() - start_mono) * 1000)
            return LLMResult(
                parsed=parsed,
                provider=self.provider_name,
                model=active_model,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=t_tok,
                latency_ms=latency_ms,
                request_id=req_id,
                raw_text=cleaned,
            )
        except (ValidationError, ValueError) as first_err:
            logger.warning(
                "Structured output validation failed; running single bounded repair attempt.",
                extra={"extra_data": {"node": trace_context.get("node"), "model": active_model}},
            )
            repair_payload = json.dumps(
                {
                    "task": "Fix the invalid JSON to satisfy the target schema.",
                    "validation_errors": str(first_err)[:1500],
                    "invalid_json": cleaned[:4000],
                },
                ensure_ascii=False,
            )
            repair_system = (
                "You repair malformed JSON payloads so they conform strictly to the requested "
                "JSON schema. Return valid JSON only without markdown fences."
            )
            (
                repaired_raw,
                rep_p_tok,
                rep_c_tok,
                rep_t_tok,
                rep_req_id,
            ) = await self._call_once(
                model=active_model,
                system_prompt=repair_system,
                payload_text=repair_payload,
                response_schema=response_schema,
                temperature=0.0,
            )
            repaired_clean = strip_json_fences(repaired_raw)
            try:
                parsed = response_schema.model_validate_json(repaired_clean)
            except (ValidationError, ValueError) as repair_err:
                raise ProviderError(
                    "PROVIDER_INVALID_OUTPUT",
                    "Model output failed schema validation after bounded repair.",
                    retryable=False,
                    cause=repair_err,
                ) from repair_err

            latency_ms = int((time.monotonic() - start_mono) * 1000)
            combined_p = (
                (p_tok + rep_p_tok) if (p_tok is not None and rep_p_tok is not None) else None
            )
            combined_c = (
                (c_tok + rep_c_tok) if (c_tok is not None and rep_c_tok is not None) else None
            )
            combined_t = (
                (t_tok + rep_t_tok) if (t_tok is not None and rep_t_tok is not None) else None
            )
            return LLMResult(
                parsed=parsed,
                provider=self.provider_name,
                model=active_model,
                prompt_tokens=combined_p,
                completion_tokens=combined_c,
                total_tokens=combined_t,
                latency_ms=latency_ms,
                request_id=rep_req_id or req_id,
                raw_text=repaired_clean,
            )
