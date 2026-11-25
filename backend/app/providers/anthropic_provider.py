import asyncio
import json
import random
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.logging import get_logger, redact_sensitive
from app.providers.base import LLMProvider, LLMResult, ProviderError, strip_json_fences

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude Messages adapter with forced tool-schema structured output."""

    provider_name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "Claude (Anthropic) API key is not configured.",
                retryable=False,
            )
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    async def _call_once(
        self,
        *,
        model: str,
        system_prompt: str,
        payload_text: str,
        response_schema: type[T],
        temperature: float,
    ) -> tuple[str, int | None, int | None, int | None, str | None]:
        url = f"{self._base_url}/messages"
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": payload_text}],
            "tools": [
                {
                    "name": "emit_structured_output",
                    "description": "Return the structured output matching the required JSON schema.",
                    "input_schema": response_schema.model_json_schema(),
                }
            ],
            "tool_choice": {"type": "tool", "name": "emit_structured_output"},
        }

        attempt = 0
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_seconds),
            transport=self._transport,
        ) as client:
            while True:
                try:
                    resp = await client.post(url, headers=self._headers(), json=body)
                except (httpx.TimeoutException, TimeoutError) as exc:
                    if attempt < self._max_retries:
                        attempt += 1
                        await asyncio.sleep(
                            min(4.0, (0.6 * (2**attempt)) + random.uniform(0.05, 0.25))
                        )
                        continue
                    raise ProviderError(
                        "PROVIDER_TIMEOUT",
                        "Claude took too long to respond. Please try again.",
                        retryable=True,
                        cause=exc,
                    ) from exc
                except httpx.HTTPError as exc:
                    if attempt < self._max_retries:
                        attempt += 1
                        await asyncio.sleep(min(4.0, 0.5 * (2**attempt)))
                        continue
                    raise ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        "Network error contacting Claude (Anthropic).",
                        retryable=True,
                        cause=exc,
                    ) from exc

                if resp.status_code in (401, 403):
                    raise ProviderError(
                        "PROVIDER_NOT_CONFIGURED",
                        "Claude (Anthropic) API key was rejected.",
                        retryable=False,
                    )

                if resp.status_code == 404:
                    raise ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        f"Claude model '{model}' was not found.",
                        retryable=False,
                    )

                if resp.status_code == 429:
                    if attempt < self._max_retries:
                        attempt += 1
                        await asyncio.sleep(
                            min(6.0, (0.8 * (2**attempt)) + random.uniform(0.1, 0.4))
                        )
                        continue
                    raise ProviderError(
                        "PROVIDER_RATE_LIMIT",
                        f"Claude rate limit reached for '{model}'.",
                        retryable=True,
                    )

                if resp.status_code >= 500:
                    if attempt < self._max_retries:
                        attempt += 1
                        await asyncio.sleep(
                            min(6.0, (0.7 * (2**attempt)) + random.uniform(0.05, 0.25))
                        )
                        continue
                    raise ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        f"Claude is temporarily busy ({resp.status_code}).",
                        retryable=True,
                    )

                if resp.status_code >= 400:
                    safe_detail = redact_sensitive(resp.text)[:180]
                    raise ProviderError(
                        "INTERNAL_ERROR",
                        f"Claude API error ({resp.status_code}): {safe_detail}",
                        retryable=False,
                    )

                data = resp.json()
                raw_json = ""
                for block in data.get("content") or []:
                    if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                        raw_json = json.dumps(block["input"], ensure_ascii=False)
                        break
                    if block.get("type") == "text" and block.get("text"):
                        raw_json = str(block["text"])

                usage = data.get("usage") or {}
                in_tok = usage.get("input_tokens")
                out_tok = usage.get("output_tokens")
                tot_tok = (
                    (in_tok + out_tok) if isinstance(in_tok, int) and isinstance(out_tok, int) else None
                )
                return raw_json, in_tok, out_tok, tot_tok, data.get("id")

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

        raw_text, p_tok, c_tok, t_tok, req_id = await self._call_once(
            model=model,
            system_prompt=system_prompt,
            payload_text=payload_text,
            response_schema=response_schema,
            temperature=temperature,
        )

        cleaned = strip_json_fences(raw_text)
        try:
            parsed = response_schema.model_validate_json(cleaned)
            return LLMResult(
                parsed=parsed,
                provider=self.provider_name,
                model=model,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                total_tokens=t_tok,
                latency_ms=int((time.monotonic() - start_mono) * 1000),
                request_id=req_id,
                raw_text=cleaned,
            )
        except (ValidationError, ValueError) as first_err:
            logger.warning(
                "Anthropic structured validation failed; running single repair attempt.",
                extra={"extra_data": {"node": trace_context.get("node"), "model": model}},
            )
            repair_payload = json.dumps(
                {
                    "task": "Fix the invalid JSON to satisfy the emit_structured_output schema.",
                    "validation_errors": str(first_err)[:1500],
                    "invalid_json": cleaned[:4000],
                },
                ensure_ascii=False,
            )
            rep_raw, rep_p, rep_c, rep_t, rep_id = await self._call_once(
                model=model,
                system_prompt="Repair the payload and emit valid JSON via emit_structured_output.",
                payload_text=repair_payload,
                response_schema=response_schema,
                temperature=0.0,
            )
            rep_clean = strip_json_fences(rep_raw)
            try:
                parsed = response_schema.model_validate_json(rep_clean)
            except (ValidationError, ValueError) as repair_err:
                raise ProviderError(
                    "PROVIDER_INVALID_OUTPUT",
                    "Claude output failed schema validation after bounded repair.",
                    retryable=False,
                    cause=repair_err,
                ) from repair_err

            combined_p = (p_tok + rep_p) if (p_tok is not None and rep_p is not None) else None
            combined_c = (c_tok + rep_c) if (c_tok is not None and rep_c is not None) else None
            combined_t = (t_tok + rep_t) if (t_tok is not None and rep_t is not None) else None
            return LLMResult(
                parsed=parsed,
                provider=self.provider_name,
                model=model,
                prompt_tokens=combined_p,
                completion_tokens=combined_c,
                total_tokens=combined_t,
                latency_ms=int((time.monotonic() - start_mono) * 1000),
                request_id=rep_id or req_id,
                raw_text=rep_clean,
            )
