from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .llm_service import (
    GeneratedResourcePlan,
    PlanningResourceLLMService,
)
from .schemas import PlanningResourceRequest
from .service import PlanningResourceService


class PlanningResourceState(TypedDict, total=False):
    request: PlanningResourceRequest
    contexts: list[dict[str, Any]]
    plans: list[GeneratedResourcePlan]
    result: dict[str, Any]


class PlanningResourceGraph:
    def __init__(
        self,
        resource_service: PlanningResourceService | None = None,
        llm_service: PlanningResourceLLMService | None = None,
    ) -> None:
        self.resource_service = resource_service or PlanningResourceService()
        self.llm_service = llm_service or PlanningResourceLLMService()
        self.graph = self._build()

    def invoke(self, request: PlanningResourceRequest) -> dict[str, Any]:
        return self.graph.invoke({"request": request})["result"]

    def _build(self):
        workflow = StateGraph(PlanningResourceState)
        workflow.add_node("prepare_contexts", self._prepare_contexts)
        workflow.add_node("estimate_resources", self._estimate_resources)
        workflow.add_node("recommend_assignments", self._recommend_assignments)

        workflow.add_edge(START, "prepare_contexts")
        workflow.add_edge("prepare_contexts", "estimate_resources")
        workflow.add_edge("estimate_resources", "recommend_assignments")
        workflow.add_edge("recommend_assignments", END)
        return workflow.compile()

    def _prepare_contexts(
        self,
        state: PlanningResourceState,
    ) -> dict[str, Any]:
        return {
            "contexts": self.resource_service.prepare_contexts(
                state["request"]
            )
        }

    def _estimate_resources(
        self,
        state: PlanningResourceState,
    ) -> dict[str, Any]:
        return {
            "plans": self.llm_service.generate(state["contexts"]),
        }

    def _recommend_assignments(
        self,
        state: PlanningResourceState,
    ) -> dict[str, Any]:
        return {
            "result": self.resource_service.build_recommendation(
                state["request"],
                state["plans"],
            )
        }
