from dataclasses import dataclass
from typing import Any

from app.prompts.registry import get_prompt_template
from app.providers.base import LLMProvider, LLMResult
from app.schemas.agents import FactualClaimCandidate, WriterDraftOutput


@dataclass(slots=True)
class WriterExecutionResult:
    draft: WriterDraftOutput
    llm_result: LLMResult[WriterDraftOutput]
    prompt_version: str


async def run_writer_agent(
    *,
    normalized_brief: dict[str, Any],
    research_brief: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    llm: LLMProvider,
    model: str,
    temperature: float = 0.3,
    prior_draft: dict[str, Any] | None = None,
    editor_result: dict[str, Any] | None = None,
    fact_check_result: dict[str, Any] | None = None,
    revision_mode: str | None = None,
    trace_context: dict[str, Any] | None = None,
) -> WriterExecutionResult:
    """Create or revise a structured social post draft grounded in the ResearchBrief."""
    tpl = get_prompt_template("writer")
    valid_ev_ids = {item["evidence_id"] for item in evidence_items if item.get("evidence_id")}

    feedback_block: dict[str, Any] = {}
    if revision_mode == "editor" and editor_result:
        feedback_block = {
            "feedback_source": "editor",
            "score": editor_result.get("score"),
            "critical_issues": editor_result.get("critical_issues", []),
            "major_issues": editor_result.get("major_issues", []),
            "rewrite_instructions": editor_result.get("rewrite_instructions", []),
        }
    elif revision_mode == "fact_check" and fact_check_result:
        feedback_block = {
            "feedback_source": "fact_checker",
            "overall_status": fact_check_result.get("overall_status"),
            "critical_findings": fact_check_result.get("critical_findings", []),
            "rewrite_instructions": fact_check_result.get("rewrite_instructions", []),
            "claims_needing_attention": [
                c
                for c in (fact_check_result.get("claims") or [])
                if c.get("status") in {"contradicted", "unsupported", "partially_supported"}
            ],
        }

    payload = {
        "brief": normalized_brief,
        "research_brief": research_brief,
        "revision_mode": revision_mode,
        "prior_draft": prior_draft,
        "feedback": feedback_block or None,
    }

    llm_result = await llm.generate_structured(
        model=model,
        system_prompt=tpl.body,
        user_payload=payload,
        response_schema=WriterDraftOutput,
        temperature=temperature,
        trace_context={**(trace_context or {}), "node": "writer"},
    )

    # Strip any fabricated evidence_ids that do not belong to the run's evidence ledger
    cleaned_claims = [
        FactualClaimCandidate(
            claim_id=c.claim_id,
            text=c.text,
            evidence_ids=[eid for eid in c.evidence_ids if eid in valid_ev_ids],
            materiality=c.materiality,
            claim_type=c.claim_type,
        )
        for c in llm_result.parsed.factual_claims
    ]
    cleaned_draft = llm_result.parsed.model_copy(update={"factual_claims": cleaned_claims})
    llm_result.parsed = cleaned_draft

    return WriterExecutionResult(
        draft=cleaned_draft,
        llm_result=llm_result,
        prompt_version=tpl.version_tag,
    )
