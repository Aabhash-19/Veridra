import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from tavily import AsyncTavilyClient

from app.core.logging import get_logger
from app.core.security import (
    UnsafeURLError,
    canonicalize_url,
    sanitize_untrusted_text,
    validate_url_ssrf_safe,
)
from app.providers.base import PageResult, ProviderError, SearchProvider, SearchResult
from app.schemas.common import utc_now_iso

logger = get_logger(__name__)

MAX_RESPONSE_BYTES = 512 * 1024  # 512 KB cap for public HTML/text extraction
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
MAX_REDIRECTS = 4


async def safe_fetch_public_page(
    url: str,
    *,
    timeout_seconds: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PageResult:
    """Fetch a public HTTP/HTTPS page with SSRF validation on every redirect hop."""
    accessed_at = utc_now_iso()
    current_url = url.strip()

    try:
        current_url = await validate_url_ssrf_safe(current_url)
    except UnsafeURLError as exc:
        return PageResult(
            original_url=url,
            canonical_url=url,
            title=urlparse(url).netloc or url,
            text_excerpt="",
            publisher=urlparse(url).netloc or None,
            published_at=None,
            fetched_at=accessed_at,
            content_type=None,
            status="inaccessible",
            error_code="UNSAFE_URL",
            error_detail=str(exc),
        )

    headers = {
        "User-Agent": "VeridraResearchBot/1.0 (+public-source-retrieval)",
        "Accept": "text/html,text/plain,application/xhtml+xml;q=0.9",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
        ) as client:
            response: httpx.Response | None = None
            for _ in range(MAX_REDIRECTS + 1):
                response = await client.get(current_url, headers=headers)
                if response.is_redirect and "location" in response.headers:
                    next_url = urljoin(current_url, response.headers["location"])
                    try:
                        current_url = await validate_url_ssrf_safe(next_url)
                    except UnsafeURLError as exc:
                        return PageResult(
                            original_url=url,
                            canonical_url=canonicalize_url(url),
                            title=urlparse(url).netloc or url,
                            text_excerpt="",
                            publisher=urlparse(url).netloc or None,
                            published_at=None,
                            fetched_at=accessed_at,
                            content_type=None,
                            status="inaccessible",
                            error_code="UNSAFE_REDIRECT",
                            error_detail=str(exc),
                        )
                    continue
                break

            if response is None:
                return PageResult(
                    original_url=url,
                    canonical_url=canonicalize_url(current_url),
                    title=urlparse(current_url).netloc or current_url,
                    text_excerpt="",
                    publisher=urlparse(current_url).netloc or None,
                    published_at=None,
                    fetched_at=accessed_at,
                    content_type=None,
                    status="failed",
                    error_code="NO_RESPONSE",
                    error_detail="No HTTP response received.",
                )

            if response.is_redirect:
                return PageResult(
                    original_url=url,
                    canonical_url=canonicalize_url(current_url),
                    title=urlparse(current_url).netloc or current_url,
                    text_excerpt="",
                    publisher=urlparse(current_url).netloc or None,
                    published_at=None,
                    fetched_at=accessed_at,
                    content_type=None,
                    status="inaccessible",
                    error_code="TOO_MANY_REDIRECTS",
                    error_detail="Exceeded maximum redirect hops.",
                )

            if response.status_code in (401, 403, 451):
                return PageResult(
                    original_url=url,
                    canonical_url=canonicalize_url(current_url),
                    title=urlparse(current_url).netloc or current_url,
                    text_excerpt="",
                    publisher=urlparse(current_url).netloc or None,
                    published_at=None,
                    fetched_at=accessed_at,
                    content_type=response.headers.get("content-type"),
                    status="inaccessible",
                    error_code=f"HTTP_{response.status_code}",
                    error_detail="Access restricted or gated by origin.",
                )

            if response.status_code >= 400:
                return PageResult(
                    original_url=url,
                    canonical_url=canonicalize_url(current_url),
                    title=urlparse(current_url).netloc or current_url,
                    text_excerpt="",
                    publisher=urlparse(current_url).netloc or None,
                    published_at=None,
                    fetched_at=accessed_at,
                    content_type=response.headers.get("content-type"),
                    status="failed",
                    error_code=f"HTTP_{response.status_code}",
                    error_detail=f"Origin returned HTTP {response.status_code}.",
                )

            raw_ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if raw_ctype and not any(
                raw_ctype.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES
            ):
                return PageResult(
                    original_url=url,
                    canonical_url=canonicalize_url(current_url),
                    title=urlparse(current_url).netloc or current_url,
                    text_excerpt="",
                    publisher=urlparse(current_url).netloc or None,
                    published_at=None,
                    fetched_at=accessed_at,
                    content_type=raw_ctype,
                    status="unsupported_content_type",
                    error_code="UNSUPPORTED_CONTENT_TYPE",
                    error_detail=f"Unsupported content type '{raw_ctype}'.",
                )

            raw_bytes = response.content[:MAX_RESPONSE_BYTES]
            truncated = len(response.content) > MAX_RESPONSE_BYTES
            text_body = raw_bytes.decode(response.encoding or "utf-8", errors="replace")

            domain = urlparse(current_url).netloc.lower()
            title = domain
            published_at: str | None = None
            canonical = canonicalize_url(current_url)

            if raw_ctype == "text/plain":
                excerpt = sanitize_untrusted_text(text_body, max_chars=2400)
            else:
                soup = BeautifulSoup(text_body, "html.parser")
                if soup.title and soup.title.string:
                    title = sanitize_untrusted_text(soup.title.string, max_chars=240) or domain
                canon_tag = soup.find("link", rel="canonical")
                if canon_tag and canon_tag.get("href"):
                    cand = str(canon_tag.get("href")).strip()
                    if cand.startswith(("http://", "https://")):
                        canonical = canonicalize_url(cand)
                pub_meta = (
                    soup.find("meta", attrs={"property": "article:published_time"})
                    or soup.find("meta", attrs={"name": "date"})
                    or soup.find("meta", attrs={"name": "pubdate"})
                )
                if pub_meta and pub_meta.get("content"):
                    published_at = str(pub_meta.get("content")).strip()[:40]
                for tag in soup(["script", "style", "noscript", "nav", "footer", "aside"]):
                    tag.decompose()
                extracted = soup.get_text(separator=" ", strip=True)
                excerpt = sanitize_untrusted_text(extracted, max_chars=2400)

            return PageResult(
                original_url=url,
                canonical_url=canonical,
                title=title,
                text_excerpt=excerpt,
                publisher=domain,
                published_at=published_at,
                fetched_at=accessed_at,
                content_type=raw_ctype or "text/html",
                status="partially_retrieved" if truncated else "retrieved",
            )
    except (httpx.TimeoutException, TimeoutError):
        return PageResult(
            original_url=url,
            canonical_url=canonicalize_url(current_url),
            title=urlparse(current_url).netloc or current_url,
            text_excerpt="",
            publisher=urlparse(current_url).netloc or None,
            published_at=None,
            fetched_at=accessed_at,
            content_type=None,
            status="failed",
            error_code="FETCH_TIMEOUT",
            error_detail="Timed out fetching public page.",
        )
    except httpx.HTTPError as exc:
        return PageResult(
            original_url=url,
            canonical_url=canonicalize_url(current_url),
            title=urlparse(current_url).netloc or current_url,
            text_excerpt="",
            publisher=urlparse(current_url).netloc or None,
            published_at=None,
            fetched_at=accessed_at,
            content_type=None,
            status="failed",
            error_code="FETCH_ERROR",
            error_detail=f"HTTP fetch error ({type(exc).__name__}).",
        )


class TavilySearchProvider(SearchProvider):
    """Tavily Search API adapter with SSRF-safe public page extraction."""

    provider_name = "tavily"

    def __init__(self, *, api_key: str, timeout_seconds: float = 20.0) -> None:
        if not api_key or not api_key.strip():
            raise ProviderError(
                "SEARCH_UNAVAILABLE",
                "Tavily API key is not configured.",
                retryable=False,
            )
        self._client = AsyncTavilyClient(api_key=api_key.strip())
        self._timeout_seconds = timeout_seconds

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        freshness: str | None = None,
        search_depth: str = "advanced",
        include_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        kwargs: dict = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max(1, min(max_results, 10)),
            "include_answer": False,
        }
        if freshness in {"day", "week", "month", "year"}:
            kwargs["time_range"] = freshness
        if include_domains:
            kwargs["include_domains"] = include_domains

        try:
            payload = await asyncio.wait_for(
                self._client.search(**kwargs),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProviderError(
                "SEARCH_UNAVAILABLE",
                "Tavily search request timed out.",
                retryable=True,
                cause=exc,
            ) from exc
        except Exception as exc:
            raise ProviderError(
                "SEARCH_UNAVAILABLE",
                f"Tavily search error ({type(exc).__name__}).",
                retryable=True,
                cause=exc,
            ) from exc

        results: list[SearchResult] = []
        for item in payload.get("results", []):
            raw_url = str(item.get("url") or "").strip()
            if not raw_url:
                continue
            domain = urlparse(raw_url).netloc.lower()
            results.append(
                SearchResult(
                    url=raw_url,
                    title=sanitize_untrusted_text(str(item.get("title") or domain), max_chars=300),
                    snippet=sanitize_untrusted_text(str(item.get("content") or ""), max_chars=1600),
                    published_at=item.get("published_date"),
                    domain=domain,
                    provider_metadata={
                        "score": item.get("score"),
                        "provider": "tavily",
                    },
                )
            )
        return results

    async def fetch_public_page(self, url: str) -> PageResult:
        return await safe_fetch_public_page(url)
