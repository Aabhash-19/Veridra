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

_PROVIDER_DISPLAY_NAMES = {
    "openai": "ChatGPT (OpenAI)",
    "groq": "Groq",
    "openrouter": "OpenRouter",
}


class OpenAICompatibleProvider(LLMProvider):
    """Structured LLM adapter for OpenAI (ChatGPT), Groq, and OpenRouter chat endpoints."""

    def __init__(
        self,
        *,
        provider_name: str = "openai",
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        display_name: str | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        extra_headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.provider_name = provider_name.lower().strip()
        self._display_name = display_name or _PROVIDER_DISPLAY_NAMES.get(
            self.provider_name, provider_name.title()
        )
        if not api_key or not api_key.strip():
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                f"{self._display_name} API key is not configured.",
                retryable=False,
            )
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._extra_headers = dict(extra_headers or {})
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

    def _build_system_instruction(self, base_prompt: str, schema: type[T]) -> str:
        schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"), ensure_ascii=False)
        return (
            f"{base_prompt.strip()}\n\n"
            "Respond with a single valid JSON object matching this exact JSON Schema "
            "(do not wrap in markdown code fences):\n"
            f"{schema_json}"
        )

    async def _call_once(
        self,
        *,
        model: str,
        system_prompt: str,
        payload_text: str,
        temperature: float,
        use_json_mode: bool = True,
    ) -> tuple[str, int | None, int | None, int | None, str | None]:
        url = f"{self._base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": payload_text},
            ],
            "temperature": temperature,
        }
        if use_json_mode:
            body["response_format"] = {"type": "json_object"}

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
                        f"{self._display_name} took too long to respond. Try again or pick another AI.",
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
                        f"Network error contacting {self._display_name}.",
                        retryable=True,
                        cause=exc,
                    ) from exc

                if resp.status_code in (401, 403):
                    raise ProviderError(
                        "PROVIDER_NOT_CONFIGURED",
                        f"{self._display_name} API key was rejected.",
                        retryable=False,
                    )

                if resp.status_code == 400 and use_json_mode and "response_format" in resp.text:
                    # Fallback gracefully for endpoints/models that reject response_format
                    use_json_mode = False
                    body.pop("response_format", None)
                    continue

                if resp.status_code == 404:
                    raise ProviderError(
                        "PROVIDER_UNAVAILABLE",
                        f"Model '{model}' was not found on {self._display_name}. Pick another model or check its name.",
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
                        f"{self._display_name} rate limit reached for '{model}'. Wait a moment or try another AI.",
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
                        f"{self._display_name} is temporarily busy ({resp.status_code}). Try again or switch AI.",
                        retryable=True,
                    )

                if resp.status_code >= 400:
                    safe_detail = redact_sensitive(resp.text)[:180]
                    raise ProviderError(
                        "INTERNAL_ERROR",
                        f"{self._display_name} error ({resp.status_code}): {safe_detail}",
                        retryable=False,
                    )

                data = resp.json()
                choices = data.get("choices") or []
                content = ""
                if choices:
                    msg = choices[0].get("message") or {}
                    content = str(msg.get("content") or "")

                usage = data.get("usage") or {}
                p_tok = usage.get("prompt_tokens")
                c_tok = usage.get("completion_tokens")
                t_tok = usage.get("total_tokens")
                if t_tok is None and isinstance(p_tok, int) and isinstance(c_tok, int):
                    t_tok = p_tok + c_tok
                req_id = data.get("id")
                return content, p_tok, c_tok, t_tok, req_id

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
        full_system = self._build_system_instruction(system_prompt, response_schema)

        raw_text, p_tok, c_tok, t_tok, req_id = await self._call_once(
            model=model,
            system_prompt=full_system,
            payload_text=payload_text,
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
                "OpenAI-compatible structured validation failed; running single repair attempt.",
                extra={
                    "extra_data": {
                        "provider": self.provider_name,
                        "node": trace_context.get("node"),
                        "model": model,
                    }
                },
            )
            repair_payload = json.dumps(
                {
                    "task": "Repair the invalid JSON to satisfy the requested JSON Schema.",
                    "validation_errors": str(first_err)[:1500],
                    "invalid_json": cleaned[:4000],
                },
                ensure_ascii=False,
            )
            repair_sys = self._build_system_instruction(
                "You repair malformed JSON payloads so they strictly match the JSON Schema.",
                response_schema,
            )
            rep_raw, rep_p, rep_c, rep_t, rep_id = await self._call_once(
                model=model,
                system_prompt=repair_sys,
                payload_text=repair_payload,
                temperature=0.0,
            )
            rep_clean = strip_json_fences(rep_raw)
            try:
                parsed = response_schema.model_validate_json(rep_clean)
            except (ValidationError, ValueError) as repair_err:
                raise ProviderError(
                    "PROVIDER_INVALID_OUTPUT",
                    f"{self._display_name} returned invalid structure after repair.",
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
