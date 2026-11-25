import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.core.security import (
    UnsafeURLError,
    canonicalize_url,
    sanitize_untrusted_text,
    validate_url_syntax,
)
from app.prompts.registry import get_prompt_template
from app.providers.base import LLMProvider, LLMResult, ProviderError, SearchProvider
from app.providers.tavily import safe_fetch_public_page
from app.schemas.agents import (
    ResearchBrief,
    ResearchEvidenceOutput,
    ResearchSourceOutput,
)
from app.schemas.common import utc_now_iso


@dataclass(slots=True)
class ResearcherExecutionResult:
    research_brief: ResearchBrief
    sources: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    llm_result: LLMResult[ResearchBrief]
    tool_latency_ms: int
    tool_calls: int
    prompt_version: str
    search_failed: bool


async def run_researcher_agent(
    *,
    normalized_brief: dict[str, Any],
    search_plan: list[dict[str, Any]],
    llm: LLMProvider,
    search: SearchProvider | None,
    model: str,
    temperature: float = 0.2,
    max_sources: int = 12,
    search_depth: str = "advanced",
    time_scope: str | None = None,
    previous_brief: dict[str, Any] | None = None,
    trace_context: dict[str, Any] | None = None,
) -> ResearcherExecutionResult:
    """Gather, deduplicate, and synthesize public/user sources into a grounded ResearchBrief."""
    tool_start = time.monotonic()
    tool_calls = 0
    warnings: list[dict[str, Any]] = []
    search_failed = False

    deduped_by_canon: dict[str, dict[str, Any]] = {}
    seen_title_domain: set[tuple[str, str]] = set()
    user_urls = list(normalized_brief.get("source_urls") or [])
    source_prefs = list(normalized_brief.get("source_preference") or [])
    include_domains = [d.strip().lower() for d in source_prefs if "." in d] or None

    # 1. Fetch validated user-supplied URLs first to preserve user-provided provenance.
    for raw_url in user_urls:
        try:
            checked_url = validate_url_syntax(raw_url)
        except UnsafeURLError as exc:
            warnings.append(
                {
                    "code": "UNSAFE_SOURCE_URL",
                    "message": f"Skipped user-supplied URL: {exc}",
                    "node": "researcher",
                }
            )
            continue

        tool_calls += 1
        page = (
            await search.fetch_public_page(checked_url)
            if search is not None
            else await safe_fetch_public_page(checked_url)
        )
        canon = page.canonical_url or canonicalize_url(checked_url)
        domain = page.publisher or urlparse(checked_url).netloc.lower()
        deduped_by_canon[canon] = {
            "url": checked_url,
            "canonical_url": canon,
            "title": page.title or domain,
            "publisher": domain,
            "published_at": page.published_at,
            "accessed_at": page.fetched_at,
            "snippet": page.text_excerpt[:600] if page.text_excerpt else (page.error_detail or ""),
            "fetched_text_excerpt": page.text_excerpt or None,
            "credibility_score": 0.90 if page.status == "retrieved" else None,
            "relevance_score": 0.92,
            "source_type": "user_supplied",
            "status": page.status,
            "fetch_error": page.error_detail,
        }
        seen_title_domain.add((page.title.lower().strip(), domain))

    # 2. Execute search queries if SearchProvider is available.
    if search is None:
        search_failed = True
        warnings.append(
            {
                "code": "SEARCH_UNAVAILABLE",
                "message": "Search provider is unavailable; using only user-supplied sources if valid.",
                "node": "researcher",
            }
        )
    else:
        for query_item in search_plan[:6]:
            if len(deduped_by_canon) >= max_sources:
                break
            query_text = str(query_item.get("query") or "").strip()
            if not query_text:
                continue
            tool_calls += 1
            try:
                hits = await search.search(
                    query_text,
                    max_results=4,
                    freshness=time_scope,
                    search_depth=search_depth,
                    include_domains=include_domains,
                )
            except ProviderError as exc:
                search_failed = True
                warnings.append(
                    {
                        "code": exc.code,
                        "message": f"Search failed for query '{query_text[:60]}': {exc.message}",
                        "node": "researcher",
                    }
                )
                break

            for hit in hits:
                if len(deduped_by_canon) >= max_sources:
                    break
                try:
                    checked_hit_url = validate_url_syntax(hit.url)
                except UnsafeURLError:
                    continue
                canon = canonicalize_url(checked_hit_url)
                domain = (hit.domain or urlparse(checked_hit_url).netloc).lower()
                title_key = (hit.title.lower().strip(), domain)
                if canon in deduped_by_canon or title_key in seen_title_domain:
                    continue

                snippet = sanitize_untrusted_text(hit.snippet, max_chars=1200)
                fetched_excerpt: str | None = snippet or None
                status = "retrieved" if snippet else "partially_retrieved"
                fetch_err: str | None = None

                # Attempt public page fetch for the top few results when snippet is short
                if len(deduped_by_canon) < 3 and len(snippet) < 220:
                    tool_calls += 1
                    page = await search.fetch_public_page(checked_hit_url)
                    if page.text_excerpt:
                        fetched_excerpt = page.text_excerpt
                        status = page.status
                    elif page.error_detail:
                        fetch_err = page.error_detail

                meta_score = hit.provider_metadata.get("score")
                rel_score = float(meta_score) if isinstance(meta_score, int | float) else 0.80
                rel_score = max(0.0, min(1.0, rel_score))
                deduped_by_canon[canon] = {
                    "url": checked_hit_url,
                    "canonical_url": canon,
                    "title": hit.title or domain,
                    "publisher": domain,
                    "published_at": hit.published_at,
                    "accessed_at": utc_now_iso(),
                    "snippet": snippet or (fetched_excerpt or "")[:400],
                    "fetched_text_excerpt": fetched_excerpt,
                    "credibility_score": None,
                    "relevance_score": rel_score,
                    "source_type": str(hit.provider_metadata.get("source_type") or "web"),
                    "status": status,
                    "fetch_error": fetch_err,
                }
                seen_title_domain.add(title_key)

    tool_latency_ms = int((time.monotonic() - tool_start) * 1000)

    # Assign stable run-scoped source_ids
    raw_sources: list[dict[str, Any]] = []
    for idx, src in enumerate(deduped_by_canon.values(), start=1):
        src_with_id = {"source_id": f"src_{idx}", **src}
        raw_sources.append(src_with_id)

    # 3. Synthesize structured ResearchBrief via LLM (or minimal safe fallback when 0 sources)
    tpl = get_prompt_template("researcher")
    usable_sources = [s for s in raw_sources if s["status"] in {"retrieved", "partially_retrieved"}]

    llm_payload = {
        "brief": {
            "topic": normalized_brief.get("topic"),
            "goal": normalized_brief.get("goal"),
            "platform": normalized_brief.get("platform"),
            "audience": normalized_brief.get("audience"),
            "depth": normalized_brief.get("depth"),
            "required_points": normalized_brief.get("required_points", []),
            "source_notes": normalized_brief.get("source_notes"),
        },
        "search_plan": search_plan,
        "previous_research_gaps": (previous_brief or {}).get("open_questions", []),
        "<untrusted_source_data>": [
            {
                "source_id": s["source_id"],
                "url": s["url"],
                "title": s["title"],
                "publisher": s["publisher"],
                "published_at": s["published_at"],
                "accessed_at": s["accessed_at"],
                "status": s["status"],
                "excerpt": (s["fetched_text_excerpt"] or s["snippet"])[:850],
            }
            for s in usable_sources[:6]
        ],
    }

    llm_result = await llm.generate_structured(
        model=model,
        system_prompt=tpl.body,
        user_payload=llm_payload,
        response_schema=ResearchBrief,
        temperature=temperature,
        trace_context={**(trace_context or {}), "node": "researcher"},
    )

    # Deterministic provenance filter: ensure LLM did not invent unknown URLs or source_ids
    raw_by_id = {s["source_id"]: s for s in raw_sources}
    valid_sources: list[ResearchSourceOutput] = []
    kept_source_ids: set[str] = set()
    for s_out in llm_result.parsed.sources:
        matched = raw_by_id.get(s_out.source_id)
        if matched is None:
            continue
        kept_source_ids.add(matched["source_id"])
        valid_sources.append(
            ResearchSourceOutput(
                source_id=matched["source_id"],
                url=matched["url"],
                title=matched["title"],
                publisher=matched["publisher"],
                published_at=matched["published_at"],
                accessed_at=matched["accessed_at"],
                relevance=matched["relevance_score"],
                source_type=matched["source_type"],
            )
        )

    # If LLM omitted retrieved sources, preserve the retrieved sources directly
    if not valid_sources and usable_sources:
        for matched in usable_sources:
            kept_source_ids.add(matched["source_id"])
            valid_sources.append(
                ResearchSourceOutput(
                    source_id=matched["source_id"],
                    url=matched["url"],
                    title=matched["title"],
                    publisher=matched["publisher"],
                    published_at=matched["published_at"],
                    accessed_at=matched["accessed_at"],
                    relevance=matched["relevance_score"],
                    source_type=matched["source_type"],
                )
            )

    valid_evidence: list[ResearchEvidenceOutput] = []
    evidence_records: list[dict[str, Any]] = []
    for ev in llm_result.parsed.evidence_items:
        if ev.source_id not in kept_source_ids:
            continue
        valid_evidence.append(ev)
        src_obj = raw_by_id[ev.source_id]
        evidence_records.append(
            {
                "evidence_id": ev.evidence_id,
                "source_id": ev.source_id,
                "source_url": src_obj["url"],
                "source_title": src_obj["title"],
                "quote_or_paraphrase": sanitize_untrusted_text(ev.excerpt, max_chars=1200),
                "location_hint": ev.location_hint,
                "related_claim_ids": [],
                "support_type": ev.role,
                "confidence": ev.confidence,
                "created_by_node": "researcher",
            }
        )

    sanitized_brief = ResearchBrief(
        research_summary=llm_result.parsed.research_summary,
        research_questions=llm_result.parsed.research_questions,
        key_findings=llm_result.parsed.key_findings,
        sources=valid_sources,
        evidence_items=valid_evidence,
        open_questions=llm_result.parsed.open_questions,
        confidence_notes=llm_result.parsed.confidence_notes,
    )

    return ResearcherExecutionResult(
        research_brief=sanitized_brief,
        sources=raw_sources,
        evidence_items=evidence_records,
        warnings=warnings,
        llm_result=llm_result,
        tool_latency_ms=tool_latency_ms,
        tool_calls=tool_calls,
        prompt_version=tpl.version_tag,
        search_failed=search_failed,
    )
