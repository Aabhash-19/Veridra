from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import GraphDependencies, make_nodes
from app.graph.routing import evaluate_evidence_decision
from app.graph.state import VeridraState


def build_veridra_graph(
    deps: GraphDependencies,
    *,
    checkpointer: Any = None,
):
    """Build and compile the explicit Veridra multi-agent LangGraph StateGraph."""
    nodes = make_nodes(deps)
    builder: StateGraph = StateGraph(VeridraState)

    for name, fn in nodes.items():
        builder.add_node(name, fn)

    builder.add_edge(START, "initialize_run")

    def after_initialize(state: VeridraState) -> Literal["plan_research", "safe_stop"]:
        return "safe_stop" if state.get("cancelled") else "plan_research"

    builder.add_conditional_edges(
        "initialize_run",
        after_initialize,
        {"plan_research": "plan_research", "safe_stop": "safe_stop"},
    )

    def after_plan(state: VeridraState) -> Literal["researcher", "safe_stop"]:
        return "safe_stop" if state.get("cancelled") else "researcher"

    builder.add_conditional_edges(
        "plan_research",
        after_plan,
        {"researcher": "researcher", "safe_stop": "safe_stop"},
    )

    def after_researcher(state: VeridraState) -> Literal["evidence_gate", "safe_stop"]:
        if state.get("cancelled") or state.get("next_route") == "safe_stop":
            return "safe_stop"
        return "evidence_gate"

    builder.add_conditional_edges(
        "researcher",
        after_researcher,
        {"evidence_gate": "evidence_gate", "safe_stop": "safe_stop"},
    )

    def after_evidence_gate(
        state: VeridraState,
    ) -> Literal["writer", "single_agent_run", "researcher", "safe_stop"]:
        return evaluate_evidence_decision(state, deps.limits)

    builder.add_conditional_edges(
        "evidence_gate",
        after_evidence_gate,
        {
            "writer": "writer",
            "single_agent_run": "single_agent_run",
            "researcher": "researcher",
            "safe_stop": "safe_stop",
        },
    )

    def after_writer(
        state: VeridraState,
    ) -> Literal["editor", "fact_checker", "safe_stop"]:
        if state.get("cancelled") or state.get("next_route") == "safe_stop":
            return "safe_stop"
        if state.get("total_step_count", 0) >= deps.limits.max_graph_steps:
            return "safe_stop"
        if (
            state.get("revision_mode") == "fact_check"
            or state.get("workflow_strategy") == "no_editor"
        ):
            return "fact_checker"
        return "editor"

    builder.add_conditional_edges(
        "writer",
        after_writer,
        {
            "editor": "editor",
            "fact_checker": "fact_checker",
            "safe_stop": "safe_stop",
        },
    )

    def after_editor(state: VeridraState) -> Literal["editor_router", "safe_stop"]:
        if state.get("cancelled") or state.get("next_route") == "safe_stop":
            return "safe_stop"
        return "editor_router"

    builder.add_conditional_edges(
        "editor",
        after_editor,
        {"editor_router": "editor_router", "safe_stop": "safe_stop"},
    )

    def after_editor_router(
        state: VeridraState,
    ) -> Literal["writer", "fact_checker", "finalizer", "safe_stop"]:
        route = state.get("next_route")
        if route in {"writer", "fact_checker", "finalizer", "safe_stop"}:
            return route  # type: ignore[return-value]
        return "safe_stop"

    builder.add_conditional_edges(
        "editor_router",
        after_editor_router,
        {
            "writer": "writer",
            "fact_checker": "fact_checker",
            "finalizer": "finalizer",
            "safe_stop": "safe_stop",
        },
    )

    def after_fact_checker(state: VeridraState) -> Literal["fact_router", "safe_stop"]:
        if state.get("cancelled") or state.get("next_route") == "safe_stop":
            return "safe_stop"
        return "fact_router"

    builder.add_conditional_edges(
        "fact_checker",
        after_fact_checker,
        {"fact_router": "fact_router", "safe_stop": "safe_stop"},
    )

    def after_fact_router(
        state: VeridraState,
    ) -> Literal["writer", "finalizer", "safe_stop"]:
        route = state.get("next_route")
        if route in {"writer", "finalizer", "safe_stop"}:
            return route  # type: ignore[return-value]
        return "safe_stop"

    builder.add_conditional_edges(
        "fact_router",
        after_fact_router,
        {
            "writer": "writer",
            "finalizer": "finalizer",
            "safe_stop": "safe_stop",
        },
    )

    def after_single_agent(state: VeridraState) -> Literal["finalizer", "safe_stop"]:
        if state.get("cancelled") or state.get("next_route") == "safe_stop":
            return "safe_stop"
        return "finalizer"

    builder.add_conditional_edges(
        "single_agent_run",
        after_single_agent,
        {"finalizer": "finalizer", "safe_stop": "safe_stop"},
    )

    builder.add_edge("finalizer", "persist_result")
    builder.add_edge("safe_stop", "persist_result")
    builder.add_edge("persist_result", END)

    return builder.compile(checkpointer=checkpointer)
