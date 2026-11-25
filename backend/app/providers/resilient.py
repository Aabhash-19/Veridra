from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.logging import get_logger
from app.providers.base import LLMProvider, LLMResult, ProviderError

T = TypeVar("T", bound=BaseModel)
logger = get_logger(__name__)

_FAILOVER_ERROR_CODES = {
    "PROVIDER_RATE_LIMIT",
    "PROVIDER_UNAVAILABLE",
    "PROVIDER_TIMEOUT",
}


class ResilientLLMProvider(LLMProvider):
    """Wraps a primary LLMProvider and fails over across configured backups on 429/503/timeout.

    Always returns the exact provider and model that actually fulfilled each step so telemetry,
    audit logs, and cost reporting stay truthful.
    """

    def __init__(
        self,
        *,
        primary_provider: LLMProvider,
        primary_model: str,
        backups: list[tuple[LLMProvider, str]],
    ) -> None:
        self._primary = primary_provider
        self._primary_model = primary_model
        self._backups = backups
        self.provider_name = primary_provider.provider_name

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
        first_model = (model or "").strip() or self._primary_model
        attempts: list[tuple[LLMProvider, str]] = [(self._primary, first_model)]
        for prov, bak_model in self._backups:
            if prov.provider_name == self._primary.provider_name and bak_model == first_model:
                continue
            attempts.append((prov, bak_model))

        last_err: ProviderError | None = None
        for idx, (prov, cand_model) in enumerate(attempts):
            try:
                return await prov.generate_structured(
                    model=cand_model,
                    system_prompt=system_prompt,
                    user_payload=user_payload,
                    response_schema=response_schema,
                    temperature=temperature,
                    trace_context=trace_context,
                )
            except ProviderError as exc:
                last_err = exc
                if exc.code in _FAILOVER_ERROR_CODES and idx + 1 < len(attempts):
                    next_prov, next_model = attempts[idx + 1]
                    logger.warning(
                        "Primary AI hit transient limit/load; failing over to next configured AI.",
                        extra={
                            "extra_data": {
                                "failed_provider": prov.provider_name,
                                "failed_model": cand_model,
                                "error_code": exc.code,
                                "next_provider": next_prov.provider_name,
                                "next_model": next_model,
                            }
                        },
                    )
                    continue
                raise

        assert last_err is not None
        raise last_err
