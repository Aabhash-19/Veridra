from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def strip_json_fences(raw: str) -> str:
    """Remove optional markdown code fences around a JSON payload."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class ProviderError(Exception):
    """Normalized provider failure carrying standard Veridra error codes."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.cause = cause


@dataclass(slots=True)
class LLMResult(Generic[T]):
    parsed: T
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    request_id: str | None = None
    raw_text: str | None = None  # Private; never expose directly in API responses


class LLMProvider(ABC):
    """Abstract interface for structured LLM generation."""

    provider_name: str = "base"

    @abstractmethod
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
        """Generate and validate a Pydantic-structured response."""


@dataclass(slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    published_at: str | None
    domain: str
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PageResult:
    original_url: str
    canonical_url: str
    title: str
    text_excerpt: str
    publisher: str | None
    published_at: str | None
    fetched_at: str
    content_type: str | None
    status: (
        str  # retrieved | partially_retrieved | inaccessible | unsupported_content_type | failed
    )
    error_code: str | None = None
    error_detail: str | None = None


class SearchProvider(ABC):
    """Abstract interface for web search and SSRF-safe public page retrieval."""

    provider_name: str = "base"

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        freshness: str | None = None,
        search_depth: str = "advanced",
        include_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        """Execute a web search and return normalized SearchResult records."""

    @abstractmethod
    async def fetch_public_page(self, url: str) -> PageResult:
        """Fetch and excerpt a public HTTP/HTTPS page with SSRF and size protections."""
