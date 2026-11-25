from dataclasses import dataclass
from typing import Any

from app.prompts.registry import get_prompt_template
from app.providers.base import LLMProvider, LLMResult
from app.schemas.agents import EditorResult


@dataclass(slots=True)
class EditorExecutionResult:
    editor_result: EditorResult
    llm_result: LLMResult[EditorResult]
    prompt_version: str


async def run_editor_agent(
    *,
    normalized_brief: dict[str, Any],
    draft: dict[str, Any],
    prior_feedback: dict[str, Any] | None,
    llm: LLMProvider,
    model: str,
    threshold: int = 85,
    temperature: float = 0.1,
    trace_context: dict[str, Any] | None = None,
) -> EditorExecutionResult:
    """Critique and score draft editorial quality using weighted rubric."""
    tpl = get_prompt_template("editor")
    payload = {
        "brief": normalized_brief,
        "draft": draft,
        "approval_threshold": threshold,
        "prior_feedback": prior_feedback,
    }
    llm_result = await llm.generate_structured(
        model=model,
        system_prompt=tpl.body,
        user_payload=payload,
        response_schema=EditorResult,
        temperature=temperature,
        trace_context={**(trace_context or {}), "node": "editor"},
    )

    # Deterministically keep score aligned with breakdown sum and prevent unsafe approve
    parsed = llm_result.parsed
    computed_score = parsed.score_breakdown.computed_total
    verdict = parsed.verdict
    if verdict == "approve" and (computed_score < threshold or parsed.critical_issues):
        verdict = "revise"

    normalized_result = parsed.model_copy(
        update={
            "score": computed_score,
            "verdict": verdict,
        }
    )
    llm_result.parsed = normalized_result

    return EditorExecutionResult(
        editor_result=normalized_result,
        llm_result=llm_result,
        prompt_version=tpl.version_tag,
    )
