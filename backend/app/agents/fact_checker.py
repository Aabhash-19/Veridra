from dataclasses import dataclass
from typing import Any

from app.prompts.registry import get_prompt_template
from app.providers.base import LLMProvider, LLMResult
from app.schemas.agents import EvaluatedClaim, FactCheckResult


@dataclass(slots=True)
class FactCheckerExecutionResult:
    fact_check_result: FactCheckResult
    llm_result: LLMResult[FactCheckResult]
    prompt_version: str


async def run_fact_checker_agent(
    *,
    normalized_brief: dict[str, Any],
    draft: dict[str, Any],
    sources: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    llm: LLMProvider,
    model: str,
    temperature: float = 0.0,
    trace_context: dict[str, Any] | None = None,
) -> FactCheckerExecutionResult:
    """Verify material factual claims strictly against collected evidence items."""
    tpl = get_prompt_template("fact_checker")
    valid_ev_ids = {item["evidence_id"] for item in evidence_items if item.get("evidence_id")}

    payload = {
        "brief": normalized_brief,
        "draft": draft,
        "<untrusted_source_data>": {
            "sources": [
                {
                    "source_id": s["source_id"],
                    "url": s["url"],
                    "title": s["title"],
                    "publisher": s["publisher"],
                    "status": s["status"],
                }
                for s in sources
            ],
            "evidence_items": [
                {
                    "evidence_id": e["evidence_id"],
                    "source_id": e["source_id"],
                    "excerpt": e["quote_or_paraphrase"],
                    "role": e.get("support_type", "supports"),
                }
                for e in evidence_items
            ],
        },
    }

    llm_result = await llm.generate_structured(
        model=model,
        system_prompt=tpl.body,
        user_payload=payload,
        response_schema=FactCheckResult,
        temperature=temperature,
        trace_context={**(trace_context or {}), "node": "fact_checker"},
    )

    # Deterministic provenance verification:
    # 1. Strip any evidence IDs not present in this run.
    # 2. A claim labeled supported/partially_supported MUST have at least one valid supporting evidence ID.
    verified_claims: list[EvaluatedClaim] = []
    for claim in llm_result.parsed.claims:
        sup_ids = [eid for eid in claim.supporting_evidence_ids if eid in valid_ev_ids]
        con_ids = [eid for eid in claim.contradicting_evidence_ids if eid in valid_ev_ids]
        status = claim.status
        action = claim.recommended_action
        explanation = claim.explanation

        if status in {"supported", "partially_supported"} and not sup_ids:
            status = "unsupported"
            action = "qualify" if action == "keep" else action
            explanation = f"{explanation} (Downgraded: no valid run evidence record linked to support this claim.)"

        if con_ids and status == "supported":
            status = "uncertain"
            action = "qualify"

        verified_claims.append(
            claim.model_copy(
                update={
                    "supporting_evidence_ids": sup_ids,
                    "contradicting_evidence_ids": con_ids,
                    "status": status,
                    "recommended_action": action,
                    "explanation": explanation,
                }
            )
        )

    material_claims = [c for c in verified_claims if c.status != "not_checked"]
    unsupported_count = sum(1 for c in material_claims if c.status == "unsupported")
    contradicted_count = sum(1 for c in material_claims if c.status == "contradicted")
    uncertain_count = sum(1 for c in material_claims if c.status == "uncertain")
    supported_like = sum(
        1 for c in material_claims if c.status in {"supported", "partially_supported"}
    )
    total_material = len(material_claims)
    coverage = round(supported_like / total_material, 4) if total_material > 0 else 1.0

    overall_status = llm_result.parsed.overall_status
    if contradicted_count > 0 or unsupported_count > 0:
        if overall_status != "blocked":
            overall_status = "needs_revision"
    elif uncertain_count > 0 or any(c.status == "partially_supported" for c in material_claims):
        if overall_status == "pass":
            overall_status = "pass_with_warnings"

    limitations = list(llm_result.parsed.limitations)
    trust_note = "Claims checked against the sources collected in this run; not an independent guarantee of truth."
    if trust_note not in limitations:
        limitations.append(trust_note)

    normalized_fc = llm_result.parsed.model_copy(
        update={
            "overall_status": overall_status,
            "claims": verified_claims,
            "evidence_coverage": coverage,
            "unsupported_count": unsupported_count,
            "contradicted_count": contradicted_count,
            "uncertain_count": uncertain_count,
            "limitations": limitations,
        }
    )
    llm_result.parsed = normalized_fc

    return FactCheckerExecutionResult(
        fact_check_result=normalized_fc,
        llm_result=llm_result,
        prompt_version=tpl.version_tag,
    )
