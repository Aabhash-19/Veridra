from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.pricing import resolve_effective_provider_and_model
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import LLMProvider, ProviderError, SearchProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockLLMProvider, MockSearchProvider
from app.providers.openai_compat import OpenAICompatibleProvider
from app.providers.resilient import ResilientLLMProvider
from app.providers.tavily import TavilySearchProvider


@dataclass(slots=True)
class ProviderBundle:
    llm: LLMProvider
    search: SearchProvider | None
    execution_mode: str  # "live" | "demo"
    warnings: list[dict]


def _build_live_llm_provider(
    provider_name: str,
    cfg: Settings,
    *,
    max_retries: int = 1,
) -> LLMProvider:
    norm = provider_name.strip().lower()
    if norm == "openai":
        if not cfg.is_openai_configured:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "ChatGPT (OpenAI) isn't connected yet. Add OPENAI_API_KEY in backend/.env, or pick another connected AI / Demo Mode.",
                retryable=False,
            )
        return OpenAICompatibleProvider(
            provider_name="openai",
            display_name="ChatGPT (OpenAI)",
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            max_retries=max_retries,
        )

    if norm == "groq":
        if not cfg.is_groq_configured:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "Groq isn't connected yet. Add GROQ_API_KEY in backend/.env, or pick another connected AI / Demo Mode.",
                retryable=False,
            )
        return OpenAICompatibleProvider(
            provider_name="groq",
            display_name="Groq",
            api_key=cfg.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
            max_retries=max_retries,
        )

    if norm == "openrouter":
        if not cfg.is_openrouter_configured:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "OpenRouter isn't connected yet. Add OPENROUTER_API_KEY in backend/.env, or pick another connected AI / Demo Mode.",
                retryable=False,
            )
        return OpenAICompatibleProvider(
            provider_name="openrouter",
            display_name="OpenRouter",
            api_key=cfg.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            extra_headers={"HTTP-Referer": cfg.app_base_url, "X-Title": cfg.app_name},
            max_retries=max_retries,
        )

    if norm == "anthropic":
        if not cfg.is_anthropic_configured:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "Claude (Anthropic) isn't connected yet. Add ANTHROPIC_API_KEY in backend/.env, or pick another connected AI / Demo Mode.",
                retryable=False,
            )
        return AnthropicProvider(api_key=cfg.anthropic_api_key, max_retries=max_retries)

    if not cfg.is_gemini_configured:
        raise ProviderError(
            "PROVIDER_NOT_CONFIGURED",
            "No live AI key is configured yet. Add GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY in backend/.env — or enable Demo Mode.",
            retryable=False,
        )
    return GeminiProvider(
        api_key=cfg.gemini_api_key,
        max_retries=max_retries,
        fallback_models=("gemini-3.5-flash", "gemini-3.5-flash-lite"),
    )


def _build_backup_chain(
    *,
    primary_provider: str,
    primary_model: str,
    cfg: Settings,
) -> list[tuple[LLMProvider, str]]:
    """Build cross-provider backup rotation using all configured keys."""
    backups: list[tuple[LLMProvider, str]] = []
    candidates: list[tuple[str, str]] = []

    if cfg.is_openrouter_configured:
        candidates.append(("openrouter", cfg.openrouter_model or "openai/gpt-4o-mini"))
    if cfg.is_groq_configured:
        candidates.append(("groq", "qwen/qwen3.8-27b"))
        candidates.append(("groq", cfg.groq_model or "openai/gpt-oss-120b"))
    if cfg.is_gemini_configured:
        candidates.append(("gemini", "gemini-3.5-flash"))
        candidates.append(("gemini", "gemini-3.5-flash-lite"))
        candidates.append(("gemini", "gemini-3.6-flash"))

    cached: dict[str, LLMProvider] = {}
    for prov_name, model_id in candidates:
        if prov_name == primary_provider and model_id == primary_model:
            continue
        if prov_name not in cached:
            cached[prov_name] = _build_live_llm_provider(prov_name, cfg, max_retries=1)
        backups.append((cached[prov_name], model_id))
    return backups


def resolve_providers(
    *,
    use_demo_mode: bool = False,
    mock_scenario: str | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
    settings: Settings | None = None,
) -> ProviderBundle:
    """Resolve live or demo LLM/search adapters without hiding missing credentials."""
    cfg = settings or get_settings()
    warnings: list[dict] = []

    if use_demo_mode or cfg.demo_mode:
        return ProviderBundle(
            llm=MockLLMProvider(scenario=mock_scenario),
            search=MockSearchProvider(scenario=mock_scenario),
            execution_mode="demo",
            warnings=[
                {
                    "code": "DEMO_MODE",
                    "message": "Executed with deterministic demo adapters (not live AI/search calls).",
                    "node": "initialize_run",
                }
            ],
        )

    provider_name, primary_model = resolve_effective_provider_and_model(
        model_override=model_override,
        provider_override=provider_override,
        settings=cfg,
    )
    primary_llm = _build_live_llm_provider(provider_name, cfg, max_retries=1)
    backups = _build_backup_chain(
        primary_provider=provider_name,
        primary_model=primary_model,
        cfg=cfg,
    )
    llm: LLMProvider = (
        ResilientLLMProvider(
            primary_provider=primary_llm,
            primary_model=primary_model,
            backups=backups,
        )
        if backups
        else primary_llm
    )

    search: SearchProvider | None = None
    if cfg.is_tavily_configured:
        search = TavilySearchProvider(api_key=cfg.tavily_api_key)
    else:
        warnings.append(
            {
                "code": "SEARCH_UNAVAILABLE",
                "message": "Tavily API key is not configured; only validated user-supplied source URLs/notes can be used.",
                "node": "researcher",
            }
        )

    return ProviderBundle(
        llm=llm,
        search=search,
        execution_mode="live",
        warnings=warnings,
    )
