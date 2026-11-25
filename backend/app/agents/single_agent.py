from dataclasses import dataclass
from typing import Any

from app.prompts.registry import get_prompt_template
from app.providers.base import LLMProvider, LLMResult
from app.schemas.agents import SingleAgentOutput


@dataclass(slots=True)
class SingleAgentExecutionResult:
    output: SingleAgentOutput
    llm_result: LLMResult[SingleAgentOutput]
    prompt_version: str


async def run_single_agent_baseline(
    *,
    normalized_brief: dict[str, Any],
    research_brief: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    llm: LLMProvider,
    model: str,
    temperature: float = 0.2,
    trace_context: dict[str, Any] | None = None,
) -> SingleAgentExecutionResult:
    """Single-agent baseline producing draft + self-review + claim check from the same research packet."""
    tpl = get_prompt_template("single_agent")
    valid_ev_ids = {item["evidence_id"] for item in evidence_items if item.get("evidence_id")}

    payload = {
        "brief": normalized_brief,
        "research_brief": research_brief,
    }
    llm_result = await llm.generate_structured(
        model=model,
        system_prompt=tpl.body,
        user_payload=payload,
        response_schema=SingleAgentOutput,
        temperature=temperature,
        trace_context={**(trace_context or {}), "node": "single_agent_run"},
    )

    parsed = llm_result.parsed
    # Enforce deterministic evidence link verification fairly here too
    verified_claims = []
    for c in parsed.fact_check.claims:
        sup = [eid for eid in c.supporting_evidence_ids if eid in valid_ev_ids]
        con = [eid for eid in c.contradicting_evidence_ids if eid in valid_ev_ids]
        status = c.status
        if status in {"supported", "partially_supported"} and not sup:
            status = "unsupported"
        verified_claims.append(
            c.model_copy(
                update={
                    "supporting_evidence_ids": sup,
                    "contradicting_evidence_ids": con,
                    "status": status,
                }
            )
        )
    material = [c for c in verified_claims if c.status != "not_checked"]
    unsupported = sum(1 for c in material if c.status == "unsupported")
    contradicted = sum(1 for c in material if c.status == "contradicted")
    uncertain = sum(1 for c in material if c.status == "uncertain")
    sup_like = sum(1 for c in material if c.status in {"supported", "partially_supported"})
    cov = round(sup_like / len(material), 4) if material else 1.0

    updated_fc = parsed.fact_check.model_copy(
        update={
            "claims": verified_claims,
            "evidence_coverage": cov,
            "unsupported_count": unsupported,
            "contradicted_count": contradicted,
            "uncertain_count": uncertain,
        }
    )
    updated_parsed = parsed.model_copy(
        update={
            "self_editor_score": parsed.self_editor_breakdown.computed_total,
            "fact_check": updated_fc,
        }
    )
    llm_result.parsed = updated_parsed

    return SingleAgentExecutionResult(
        output=updated_parsed,
        llm_result=llm_result,
        prompt_version=tpl.version_tag,
    )
