import json
from typing import Any, Literal, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel

from app.core.security import canonicalize_url, sanitize_untrusted_text
from app.providers.base import (
    LLMProvider,
    LLMResult,
    PageResult,
    ProviderError,
    SearchProvider,
    SearchResult,
)
from app.providers.tavily import safe_fetch_public_page
from app.schemas.agents import (
    EditorResult,
    EvaluatedClaim,
    FactCheckResult,
    FactualClaimCandidate,
    ResearchBrief,
    ResearchEvidenceOutput,
    ResearchFindingOutput,
    ResearchSourceOutput,
    ScoreBreakdown,
    SingleAgentOutput,
    WriterDraftOutput,
)
from app.schemas.common import utc_now_iso

T = TypeVar("T", bound=BaseModel)


class MockSearchProvider(SearchProvider):
    """Deterministic demo/test search adapter. Never claims live internet search occurred."""

    provider_name = "mock"

    def __init__(self, *, scenario: str | None = None, allow_live_fetch: bool = False) -> None:
        self.scenario = scenario or "happy_path"
        self.allow_live_fetch = allow_live_fetch

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        freshness: str | None = None,
        search_depth: str = "advanced",
        include_domains: list[str] | None = None,
    ) -> list[SearchResult]:
        if self.scenario == "search_unavailable":
            raise ProviderError(
                "SEARCH_UNAVAILABLE",
                "Simulated search provider outage in test scenario.",
                retryable=False,
            )
        if self.scenario == "insufficient_evidence":
            return []

        lower = query.lower()
        now = "2026-11-20"
        if "icpc" in lower or "competitive programming" in lower:
            items = [
                SearchResult(
                    url="https://icpc.global/worldfinals/rules",
                    title="ICPC Official Rules and Team Contest Format (Demo Reference)",
                    snippet=(
                        "The International Collegiate Programming Contest (ICPC) is a multi-tier "
                        "algorithmic programming competition for university teams of three students "
                        "sharing one workstation for five hours to solve complex algorithmic problems."
                    ),
                    published_at="2025-09-10",
                    domain="icpc.global",
                    provider_metadata={"demo": True, "score": 0.94, "source_type": "primary"},
                ),
                SearchResult(
                    url="https://cacm.acm.org/practice/algorithmic-problem-solving-education",
                    title="Transferable Debugging and Constraint Analysis in CS Education (Demo Reference)",
                    snippet=(
                        "Timed problem-solving drills reinforce complexity analysis, edge-case "
                        "testing, and decomposing ambiguous specifications under time pressure."
                    ),
                    published_at="2025-05-14",
                    domain="cacm.acm.org",
                    provider_metadata={"demo": True, "score": 0.89, "source_type": "secondary"},
                ),
                SearchResult(
                    url="https://cp-algorithms.com/navigation.html",
                    title="CP-Algorithms Study Roadmap and Core Data Structures (Demo Reference)",
                    snippet=(
                        "Structured practice typically spans graphs, dynamic programming, greedy "
                        "proofs, and careful implementation verification."
                    ),
                    published_at=now,
                    domain="cp-algorithms.com",
                    provider_metadata={"demo": True, "score": 0.85, "source_type": "educational"},
                ),
            ]
        else:
            slug = "-".join(w for w in query.lower().split()[:5] if w.isalnum()) or "topic-brief"
            items = [
                SearchResult(
                    url=f"https://docs.veridra-demo.org/guides/{slug}",
                    title=f"Primary Overview: {query[:70]} (Demo Source)",
                    snippet=(
                        f"Demo reference overview examining {query[:120]}. Emphasizes measurable "
                        "workflow design, clear scope boundaries, and explicit uncertainty disclosure."
                    ),
                    published_at=now,
                    domain="docs.veridra-demo.org",
                    provider_metadata={"demo": True, "score": 0.90, "source_type": "primary"},
                ),
                SearchResult(
                    url=f"https://research.veridra-demo.org/notes/{slug}",
                    title=f"Analytical Commentary on {query[:65]} (Demo Source)",
                    snippet=(
                        f"Empirical commentary comparing practical adoption trade-offs for {query[:100]}, "
                        "noting that outcomes vary across team maturity and evaluation criteria."
                    ),
                    published_at="2026-08-02",
                    domain="research.veridra-demo.org",
                    provider_metadata={"demo": True, "score": 0.84, "source_type": "secondary"},
                ),
            ]
        return items[:max_results]

    async def fetch_public_page(self, url: str) -> PageResult:
        if self.allow_live_fetch:
            return await safe_fetch_public_page(url)
        domain = urlparse(url).netloc or "demo.local"
        return PageResult(
            original_url=url,
            canonical_url=canonicalize_url(url),
            title=f"Retrieved Excerpt from {domain} (Demo Fetch)",
            text_excerpt=sanitize_untrusted_text(
                f"Demo fetched excerpt for {url}. Use only verified details directly stated here.",
                max_chars=400,
            ),
            publisher=domain,
            published_at=None,
            fetched_at=utc_now_iso(),
            content_type="text/html",
            status="retrieved",
        )


class MockLLMProvider(LLMProvider):
    """Deterministic LLM adapter for Demo Mode and automated testing."""

    provider_name = "mock"

    def __init__(self, *, scenario: str | None = None) -> None:
        self.scenario = scenario or "happy_path"
        self._call_counts: dict[str, int] = {}

    def _bump(self, key: str) -> int:
        self._call_counts[key] = self._call_counts.get(key, 0) + 1
        return self._call_counts[key]

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
        node = str(trace_context.get("node") or response_schema.__name__)
        call_num = self._bump(node)

        if self.scenario == "provider_rate_limit":
            raise ProviderError(
                "PROVIDER_RATE_LIMIT",
                "Simulated provider rate limit (429).",
                retryable=True,
            )
        if self.scenario == "provider_timeout":
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                "Simulated provider timeout.",
                retryable=True,
            )
        if self.scenario == "malformed_json":
            raise ProviderError(
                "PROVIDER_INVALID_OUTPUT",
                "Simulated malformed JSON output that failed repair.",
                retryable=False,
            )

        parsed: BaseModel
        if response_schema is ResearchBrief:
            parsed = self._build_research_brief(user_payload)
        elif response_schema is WriterDraftOutput:
            parsed = self._build_writer_draft(user_payload, call_num)
        elif response_schema is EditorResult:
            parsed = self._build_editor_result(user_payload, call_num)
        elif response_schema is FactCheckResult:
            parsed = self._build_fact_check_result(user_payload, call_num)
        elif response_schema is SingleAgentOutput:
            parsed = self._build_single_agent_output(user_payload)
        else:
            raise ProviderError(
                "INTERNAL_ERROR",
                f"MockLLMProvider does not support schema {response_schema.__name__}.",
            )

        return LLMResult(
            parsed=parsed,  # type: ignore[arg-type]
            provider=self.provider_name,
            model=model or "mock-deterministic-v1",
            prompt_tokens=None,  # Demo mode does not fabricate real provider token usage
            completion_tokens=None,
            total_tokens=None,
            latency_ms=12,
            request_id=f"mock_{node}_{call_num}",
            raw_text=json.dumps(parsed.model_dump()),
        )

    def _build_research_brief(self, payload: dict[str, Any]) -> ResearchBrief:
        brief = payload.get("brief", {})
        topic = str(brief.get("topic") or "Topic")
        retrieved_sources = (
            payload.get("<untrusted_source_data>") or payload.get("retrieved_sources") or []
        )
        source_notes = brief.get("source_notes")

        sources_out: list[ResearchSourceOutput] = []
        evidence_out: list[ResearchEvidenceOutput] = []
        findings_out: list[ResearchFindingOutput] = []

        for idx, src in enumerate(retrieved_sources[:6], start=1):
            sid = src.get("source_id") or f"src_{idx}"
            ev_id = f"ev_{idx}"
            snippet = str(src.get("snippet") or src.get("fetched_text_excerpt") or "").strip()
            if len(snippet) < 10:
                snippet = f"Reference context retrieved for {src.get('title', sid)}."
            sources_out.append(
                ResearchSourceOutput(
                    source_id=sid,
                    url=str(src["url"]),
                    title=str(src.get("title") or sid),
                    publisher=str(src.get("publisher") or "unknown"),
                    published_at=src.get("published_at"),
                    accessed_at=str(src.get("accessed_at") or utc_now_iso()),
                    relevance=float(src.get("relevance_score") or 0.88),
                    source_type=str(src.get("source_type") or "secondary"),
                )
            )
            evidence_out.append(
                ResearchEvidenceOutput(
                    evidence_id=ev_id,
                    source_id=sid,
                    excerpt=snippet[:600],
                    role="supports",
                    location_hint="Summary excerpt",
                    supports=[f"Context supporting '{topic[:80]}'"],
                    confidence=0.85,
                )
            )
            findings_out.append(
                ResearchFindingOutput(
                    finding=snippet[:240],
                    evidence_ids=[ev_id],
                )
            )

        if source_notes and not evidence_out:
            findings_out.append(
                ResearchFindingOutput(finding=str(source_notes)[:240], evidence_ids=[])
            )

        open_questions = [
            "Specific quantitative career outcomes depend on individual context and are not uniform.",
        ]
        if len(sources_out) < 2:
            open_questions.append("Limited independent corroboration retrieved in this run.")

        return ResearchBrief(
            research_summary=(
                f"Demo-mode synthesis for '{topic}' based on {len(sources_out)} collected source(s). "
                "Claims are bounded strictly to retrieved excerpts; unproven outcomes remain flagged."
            ),
            research_questions=[
                f"What foundational context defines {topic[:90]}?",
                "Which practical implications are supported by retrieved sources?",
                "Where is direct quantitative evidence missing or context-dependent?",
            ],
            key_findings=findings_out,
            sources=sources_out,
            evidence_items=evidence_out,
            open_questions=open_questions,
            confidence_notes=[
                "Deterministic demo research adapter output; connect Tavily & Gemini keys for live research."
            ],
        )

    def _build_writer_draft(self, payload: dict[str, Any], call_num: int) -> WriterDraftOutput:
        brief = payload.get("brief", {})
        rb = payload.get("research_brief") or {}
        topic = str(brief.get("topic") or "Topic")
        platform = str(brief.get("platform") or "linkedin")
        audience = str(brief.get("audience") or "Practitioners and learners")
        cta = brief.get("call_to_action")
        req_points = brief.get("required_points") or []
        ev_items = rb.get("evidence_items") or []
        ev_ids = [item.get("evidence_id") for item in ev_items if item.get("evidence_id")]
        primary_ev = ev_ids[:1]
        secondary_ev = ev_ids[1:2] or primary_ev

        revision_mode = payload.get("revision_mode")
        rev_summary = None
        if revision_mode == "editor":
            rev_summary = (
                "Tightened opening hook, improved scannability, and clarified actionable takeaways."
            )
        elif revision_mode == "fact_check":
            rev_summary = (
                "Qualified broad outcome phrasing and removed unproven causal generalization."
            )

        # Support testing scenarios with controlled claim precision
        is_first_fact_check_draft = (
            self.scenario == "fact_remediation" and revision_mode != "fact_check"
        )
        if is_first_fact_check_draft:
            claim2_text = "Competitive programming guarantees faster promotion across every engineering career track."
            claim2_evs: list[str] = []
        elif self.scenario == "contradiction_stop":
            claim2_text = "ICPC teams compete individually for 24 hours without collaboration."
            claim2_evs = primary_ev
        else:
            claim2_text = (
                "Timed problem-solving practice reinforces algorithmic analysis, edge-case checking, "
                "and structured decomposition under constraints."
            )
            claim2_evs = secondary_ev

        if "icpc" in topic.lower() or "competitive programming" in topic.lower():
            claim1_text = (
                "In ICPC, university teams of three students collaborate on one workstation over a "
                "five-hour contest window to solve algorithmic problems."
            )
        else:
            claim1_text = (
                f"Collected reference notes for {topic[:80]} highlight clear scope boundaries and "
                "evidence-linked framing."
            )

        claims = [
            FactualClaimCandidate(
                claim_id="cl_1",
                text=claim1_text,
                evidence_ids=primary_ev,
                materiality="high",
                claim_type="factual",
            ),
            FactualClaimCandidate(
                claim_id="cl_2",
                text=claim2_text,
                evidence_ids=claim2_evs,
                materiality="high",
                claim_type="factual",
            ),
        ]

        title = (
            "What competitive programming builds beyond contest rankings"
            if "icpc" in topic.lower()
            else f"Evidence-grounded perspective: {topic[:70]}"
        )
        hook = (
            "Most people think competitive programming is just memorizing trick algorithms—but the real value shows up in how you debug under pressure."
            if revision_mode
            else f"Exploring {topic[:90]} with a practical lens for {audience}."
        )

        req_block = ""
        if req_points:
            bullets = "\n".join(f"- {pt}" for pt in req_points[:5])
            req_block = f"\n\nKey areas covered:\n{bullets}"

        cta_block = (
            f"\n\n{cta}"
            if cta
            else "\n\nWhat practices have improved your problem-solving workflow most?"
        )

        if platform == "x":
            segments = [
                f"1/ {hook} [1]",
                f"2/ {claim1_text} [1]",
                f"3/ {claim2_text} [2]",
                f"4/ Where to start: focus on core data structures, test edge cases intentionally, and review solutions thoughtfully.{cta_block.strip()}",
            ]
            body = "\n\n".join(segments)
        elif platform == "instagram":
            segments = []
            body = (
                f"{hook}\n\n"
                f"{claim1_text} [1]\n\n"
                f"{claim2_text} [2]{req_block}\n\n"
                f"{cta_block.strip()}\n\n#SoftwareEngineering #ProblemSolving #LearningInPublic"
            )
        else:
            segments = []
            body = (
                f"{hook}\n\n"
                f"{claim1_text} [1]\n\n"
                f"Why it transfers to real engineering:\n"
                f"- Reading specifications closely before writing code\n"
                f"- Stress-testing edge cases and time/space trade-offs [2]\n"
                f"- Communicating clearly when collaborating under constraints\n\n"
                f"{claim2_text}{req_block}"
                f"{cta_block}"
            )

        return WriterDraftOutput(
            title=title,
            hook=hook,
            body_markdown=body,
            outline=[
                "Opening angle grounded in practical engineering habits",
                "Verified contest/domain context",
                "Transferable skills & structured learning path",
                "Balanced close & reader prompt",
            ],
            factual_claims=claims,
            opinion_statements=[
                "Treating problems as structured design exercises yields more value than chasing leaderboard speed alone."
            ],
            platform_notes=[f"Formatted for {platform} readability."],
            thread_segments=segments,
            revision_summary=rev_summary,
        )

    def _build_editor_result(self, payload: dict[str, Any], call_num: int) -> EditorResult:
        if self.scenario == "editor_revision" and call_num == 1:
            breakdown = ScoreBreakdown(
                clarity=15,
                depth=15,
                audience=12,
                structure=11,
                platform_fit=12,
                specificity=8,
                tone=4,
            )
            return EditorResult(
                score=breakdown.computed_total,  # 77 < 85
                score_breakdown=breakdown,
                verdict="revise",
                critical_issues=[],
                major_issues=[
                    "Opening hook is generic and transitions between paragraphs need tightening."
                ],
                minor_issues=["Clarify the actionable takeaway before the close."],
                rewrite_instructions=[
                    "Sharpen the first two lines to state the core tension immediately.",
                    "Use tighter bullet phrasing for transferable skills.",
                ],
                summary="Solid evidence base, but the opening and flow need one editorial revision.",
            )
        if self.scenario == "editor_max_revisions":
            breakdown = ScoreBreakdown(
                clarity=14,
                depth=14,
                audience=11,
                structure=11,
                platform_fit=11,
                specificity=7,
                tone=4,
            )
            return EditorResult(
                score=breakdown.computed_total,  # 72 < 85 every time
                score_breakdown=breakdown,
                verdict="revise",
                critical_issues=[],
                major_issues=["Draft still falls below target editorial density."],
                minor_issues=[],
                rewrite_instructions=["Increase analytical depth and sharpen transitions."],
                summary=f"Revision pass {call_num} remains below threshold.",
            )

        breakdown = ScoreBreakdown(
            clarity=18, depth=18, audience=14, structure=13, platform_fit=13, specificity=9, tone=4
        )
        return EditorResult(
            score=breakdown.computed_total,  # 89 >= 85
            score_breakdown=breakdown,
            verdict="approve",
            critical_issues=[],
            major_issues=[],
            minor_issues=["Optional: keep closing prompt crisp."],
            rewrite_instructions=[],
            summary="Clear structure, strong audience fit, and restrained tone.",
        )

    def _build_fact_check_result(self, payload: dict[str, Any], call_num: int) -> FactCheckResult:
        draft = payload.get("draft") or {}
        claims = draft.get("factual_claims") or []
        untrusted = payload.get("<untrusted_source_data>") or {}
        ev_items = untrusted.get("evidence_items") or payload.get("evidence_items") or []
        valid_ev_ids = {item.get("evidence_id") for item in ev_items if item.get("evidence_id")}

        evaluated: list[EvaluatedClaim] = []
        unsupported_count = 0
        contradicted_count = 0
        uncertain_count = 0

        for idx, c in enumerate(claims, start=1):
            cid = str(c.get("claim_id") or f"cl_{idx}")
            text = str(c.get("text") or "")
            linked = [eid for eid in (c.get("evidence_ids") or []) if eid in valid_ev_ids]
            raw_mat = str(c.get("materiality") or "medium")
            materiality: Literal["high", "medium", "low"] = (
                raw_mat if raw_mat in {"high", "medium", "low"} else "medium"  # type: ignore[assignment]
            )

            if self.scenario == "contradiction_stop" and idx == 2:
                contradicted_count += 1
                evaluated.append(
                    EvaluatedClaim(
                        claim_id=cid,
                        claim_text=text,
                        materiality="high",
                        status="contradicted",
                        confidence=0.92,
                        supporting_evidence_ids=[],
                        contradicting_evidence_ids=linked or list(valid_ev_ids)[:1],
                        explanation="Retrieved official contest rules state teams of three share one workstation for five hours, contradicting 'individually for 24 hours'.",
                        recommended_action="correct",
                    )
                )
            elif self.scenario == "uncertain_claim" and idx == 2:
                uncertain_count += 1
                evaluated.append(
                    EvaluatedClaim(
                        claim_id=cid,
                        claim_text=text,
                        materiality=materiality,
                        status="uncertain",
                        confidence=0.45,
                        supporting_evidence_ids=linked,
                        contradicting_evidence_ids=[],
                        explanation="Evidence is context-dependent and mixed across cohorts; retain only with explicit qualification.",
                        recommended_action="qualify",
                    )
                )
            elif (
                (self.scenario == "fact_remediation" and call_num == 1 and idx == 2)
                or self.scenario == "fact_max_remediations"
                or not linked
            ):
                unsupported_count += 1
                evaluated.append(
                    EvaluatedClaim(
                        claim_id=cid,
                        claim_text=text,
                        materiality=materiality,
                        status="unsupported",
                        confidence=0.25,
                        supporting_evidence_ids=[],
                        contradicting_evidence_ids=[],
                        explanation="No retrieved source in this run supports a universal causal guarantee.",
                        recommended_action="qualify",
                    )
                )
            else:
                evaluated.append(
                    EvaluatedClaim(
                        claim_id=cid,
                        claim_text=text,
                        materiality=materiality,
                        status="supported",
                        confidence=0.88,
                        supporting_evidence_ids=linked,
                        contradicting_evidence_ids=[],
                        explanation="Directly supported by collected source excerpts in this run.",
                        recommended_action="keep",
                    )
                )

        total = len(evaluated)
        supported_like = sum(
            1 for item in evaluated if item.status in {"supported", "partially_supported"}
        )
        coverage = round(supported_like / total, 4) if total > 0 else 1.0

        if contradicted_count > 0 or unsupported_count > 0:
            overall = "needs_revision"
            rewrite = [
                "Qualify or remove unsupported/contradicted claims to match retrieved evidence."
            ]
        elif uncertain_count > 0:
            overall = "pass_with_warnings"
            rewrite = []
        else:
            overall = "pass"
            rewrite = []

        return FactCheckResult(
            overall_status=overall,  # type: ignore[arg-type]
            claims=evaluated,
            evidence_coverage=coverage,
            unsupported_count=unsupported_count,
            contradicted_count=contradicted_count,
            uncertain_count=uncertain_count,
            critical_findings=(
                ["Material contradiction detected against collected source."]
                if contradicted_count > 0
                else []
            ),
            rewrite_instructions=rewrite,
            limitations=[
                "Claims were checked only against sources collected in this run (Demo Mode)."
            ],
        )

    def _build_single_agent_output(self, payload: dict[str, Any]) -> SingleAgentOutput:
        draft = self._build_writer_draft(payload, 1)
        breakdown = ScoreBreakdown(
            clarity=16, depth=15, audience=13, structure=12, platform_fit=13, specificity=7, tone=4
        )
        ev_items = (payload.get("research_brief") or {}).get("evidence_items") or []
        valid_ids = [i.get("evidence_id") for i in ev_items if i.get("evidence_id")]
        fc_claims = [
            EvaluatedClaim(
                claim_id=c.claim_id,
                claim_text=c.text,
                materiality=c.materiality,
                status="supported" if valid_ids else "unsupported",
                confidence=0.72 if valid_ids else 0.25,
                supporting_evidence_ids=valid_ids[:1] if valid_ids else [],
                contradicting_evidence_ids=[],
                explanation="Single-agent self-check against retrieved packet.",
                recommended_action="keep" if valid_ids else "qualify",
            )
            for c in draft.factual_claims
        ]
        return SingleAgentOutput(
            draft=draft,
            self_editor_score=breakdown.computed_total,  # 80
            self_editor_breakdown=breakdown,
            self_editor_summary="Single-agent baseline draft with inline self-check (no independent reviewer loop).",
            fact_check=FactCheckResult(
                overall_status="pass_with_warnings",
                claims=fc_claims,
                evidence_coverage=1.0 if valid_ids else 0.0,
                unsupported_count=0 if valid_ids else len(fc_claims),
                contradicted_count=0,
                uncertain_count=0,
                limitations=[
                    "Single-agent self-evaluation without separate Editor or Fact Checker loop."
                ],
            ),
        )
