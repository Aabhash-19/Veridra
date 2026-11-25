from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

RATE_CARD_VERSION = "2026-11-v1"
RATE_CARD_EFFECTIVE_DATE = "2026-11-01"
CURRENCY = "USD"


@dataclass(frozen=True)
class ModelRate:
    input_price_per_million: float
    output_price_per_million: float


# Versioned reference rates (USD per 1M tokens). Unlisted models return unavailable cost.
MODEL_RATE_CARD: dict[tuple[str, str], ModelRate] = {
    ("gemini", "gemini-2.5-flash"): ModelRate(
        input_price_per_million=0.15,
        output_price_per_million=0.60,
    ),
    ("gemini", "gemini-2.5-pro"): ModelRate(
        input_price_per_million=1.25,
        output_price_per_million=10.00,
    ),
    ("gemini", "gemini-2.0-flash"): ModelRate(
        input_price_per_million=0.10,
        output_price_per_million=0.40,
    ),
}

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

# Models retired or restricted for new Google AI keys are mapped cleanly to active replacements
# so legacy .env settings or saved browser defaults work reliably and log honestly.
RETIRED_GEMINI_MODEL_ALIASES: dict[str, str] = {
    "gemini-2.5-flash": "gemini-3.6-flash",
    "gemini-2.5-pro": "gemini-3.8-flash",
    "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.0-flash": "gemini-3.5-flash-lite",
    "gemini-1.5-flash": "gemini-3.5-flash",
    "gemini-1.5-pro": "gemini-3.8-flash",
}


def resolve_live_gemini_model(model: str | None) -> str:
    """Resolve empty or retired Gemini model IDs to active verified model names."""
    cleaned = (model or "").strip()
    if not cleaned:
        return DEFAULT_GEMINI_MODEL
    return RETIRED_GEMINI_MODEL_ALIASES.get(cleaned.lower(), cleaned)


SUPPORTED_AI_MODELS: list[dict[str, object]] = [
    {
        "id": "gpt-4o-mini",
        "label": "ChatGPT (GPT-4o mini)",
        "provider": "openai",
        "tier": "Fast & Popular",
        "description": "Reliable everyday ChatGPT writer with crisp structure and low rate limits.",
        "input_price_per_million": None,
        "output_price_per_million": None,
    },
    {
        "id": "gpt-4o",
        "label": "ChatGPT (GPT-4o)",
        "provider": "openai",
        "tier": "Flagship OpenAI",
        "description": "High-craft ChatGPT model for nuanced hooks and long-form storytelling.",
        "input_price_per_million": None,
        "output_price_per_million": None,
    },
    {
        "id": "openai/gpt-oss-120b",
        "label": "GPT-OSS 120B (Groq)",
        "provider": "groq",
        "tier": "Ultra Fast",
        "description": "Very fast open AI on Groq — great high-speed free-tier writer outside Google.",
        "input_price_per_million": None,
        "output_price_per_million": None,
    },
    {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o mini (OpenRouter)",
        "provider": "openrouter",
        "tier": "Multi-AI Hub",
        "description": "Run ChatGPT and dozens of AI models using a single OpenRouter key.",
        "input_price_per_million": None,
        "output_price_per_million": None,
    },
    {
        "id": "gemini-3.6-flash",
        "label": "Gemini 3.6 Flash",
        "provider": "gemini",
        "tier": "Everyday Gemini",
        "description": "Google Gemini writer with automatic backup if Google servers get busy.",
        "input_price_per_million": None,
        "output_price_per_million": None,
    },
    {
        "id": "gemini-3.5-flash",
        "label": "Gemini 3.5 Flash",
        "provider": "gemini",
        "tier": "Steady Gemini",
        "description": "Reliable Google Gemini model with lower traffic congestion.",
        "input_price_per_million": None,
        "output_price_per_million": None,
    },
]

# Backward-compatible export
SUPPORTED_GEMINI_MODELS = SUPPORTED_AI_MODELS

_KNOWN_MODEL_PROVIDERS: dict[str, str] = {
    str(item["id"]).lower(): str(item["provider"]).lower() for item in SUPPORTED_AI_MODELS
}


def infer_provider_for_model(
    model: str | None,
    *,
    explicit_provider: str | None = None,
    fallback_provider: str = "gemini",
) -> str:
    """Infer provider adapter from explicit override, catalog, or model naming conventions."""
    if explicit_provider and explicit_provider.strip():
        return explicit_provider.strip().lower()

    cleaned = (model or "").strip().lower()
    if not cleaned:
        return fallback_provider.strip().lower() or "gemini"

    if cleaned in _KNOWN_MODEL_PROVIDERS:
        return _KNOWN_MODEL_PROVIDERS[cleaned]
    if "/" in cleaned:
        return "openrouter"
    if cleaned.startswith(("gpt-", "o1-", "o3-", "o4-", "chatgpt-")):
        return "openai"
    if cleaned.startswith("claude-"):
        return "anthropic"
    if cleaned.startswith(("llama-", "mixtral-", "qwen-", "gemma2-")):
        return "groq"
    if cleaned.startswith("gemini-"):
        return "gemini"
    return fallback_provider.strip().lower() or "gemini"


def resolve_default_model_for_provider(provider: str, settings: Any) -> str:
    """Return configured default model ID for a given provider."""
    norm = provider.strip().lower()
    if norm == "openai":
        return str(getattr(settings, "openai_model", "gpt-4o-mini")).strip() or "gpt-4o-mini"
    if norm == "groq":
        return (
            str(getattr(settings, "groq_model", "llama-3.3-70b-versatile")).strip()
            or "llama-3.3-70b-versatile"
        )
    if norm == "openrouter":
        return (
            str(getattr(settings, "openrouter_model", "openai/gpt-4o-mini")).strip()
            or "openai/gpt-4o-mini"
        )
    if norm == "anthropic":
        return (
            str(getattr(settings, "anthropic_model", "claude-3-5-haiku-latest")).strip()
            or "claude-3-5-haiku-latest"
        )
    return resolve_live_gemini_model(getattr(settings, "gemini_model", DEFAULT_GEMINI_MODEL))


def resolve_effective_provider_and_model(
    *,
    model_override: str | None,
    provider_override: str | None = None,
    settings: Any = None,
) -> tuple[str, str]:
    """Resolve concrete (provider_name, model_id) pair cleanly."""
    fallback_prov = (
        getattr(settings, "active_default_provider", "gemini") if settings is not None else "gemini"
    )
    provider = infer_provider_for_model(
        model_override,
        explicit_provider=provider_override,
        fallback_provider=fallback_prov,
    )
    cleaned_model = (model_override or "").strip()
    if not cleaned_model:
        model = (
            resolve_default_model_for_provider(provider, settings)
            if settings is not None
            else DEFAULT_GEMINI_MODEL
        )
    elif provider == "gemini":
        model = resolve_live_gemini_model(cleaned_model)
    else:
        model = cleaned_model
    return provider, model


@dataclass(frozen=True)
class CostEstimate:
    estimated_cost: float | None
    cost_status: Literal["measured_estimated", "partial", "unavailable"]
    provider: str
    model: str
    rate_card_version: str | None
    rate_card_effective_date: str | None
    input_price_per_million: float | None
    output_price_per_million: float | None
    currency: str | None
    calculated_at: str

    def to_dict(self) -> dict:
        return {
            "estimated_cost": self.estimated_cost,
            "cost_status": self.cost_status,
            "provider": self.provider,
            "model": self.model,
            "rate_card_version": self.rate_card_version,
            "rate_card_effective_date": self.rate_card_effective_date,
            "input_price_per_million": self.input_price_per_million,
            "output_price_per_million": self.output_price_per_million,
            "currency": self.currency,
            "calculated_at": self.calculated_at,
        }


def calculate_node_cost(
    *,
    provider: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    tool_costs: float = 0.0,
) -> CostEstimate:
    """Compute versioned cost estimate or mark unavailable when usage or rates are absent."""
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    norm_provider = provider.lower().strip()
    norm_model = model.strip()

    # Never invent real monetary costs for mock/demo runs or missing token counts.
    if norm_provider in {"mock", "demo"}:
        return CostEstimate(
            estimated_cost=None,
            cost_status="unavailable",
            provider=norm_provider,
            model=norm_model,
            rate_card_version=None,
            rate_card_effective_date=None,
            input_price_per_million=None,
            output_price_per_million=None,
            currency=None,
            calculated_at=now_iso,
        )

    rate = MODEL_RATE_CARD.get((norm_provider, norm_model))
    if rate is None or prompt_tokens is None or completion_tokens is None:
        return CostEstimate(
            estimated_cost=None,
            cost_status="unavailable",
            provider=norm_provider,
            model=norm_model,
            rate_card_version=RATE_CARD_VERSION if rate else None,
            rate_card_effective_date=RATE_CARD_EFFECTIVE_DATE if rate else None,
            input_price_per_million=rate.input_price_per_million if rate else None,
            output_price_per_million=rate.output_price_per_million if rate else None,
            currency=CURRENCY if rate else None,
            calculated_at=now_iso,
        )

    amount = (
        (prompt_tokens / 1_000_000.0) * rate.input_price_per_million
        + (completion_tokens / 1_000_000.0) * rate.output_price_per_million
        + tool_costs
    )
    return CostEstimate(
        estimated_cost=round(amount, 8),
        cost_status="measured_estimated",
        provider=norm_provider,
        model=norm_model,
        rate_card_version=RATE_CARD_VERSION,
        rate_card_effective_date=RATE_CARD_EFFECTIVE_DATE,
        input_price_per_million=rate.input_price_per_million,
        output_price_per_million=rate.output_price_per_million,
        currency=CURRENCY,
        calculated_at=now_iso,
    )
