from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.planning_cost import PlanningCostRequest
from app.services.planning_cost_llm_service import (
    GeneratedCostAnalysis,
    PlanningCostLLMService,
)
from app.services.planning_cost_service import PlanningCostService


class PlanningCostState(TypedDict, total=False):
    request: PlanningCostRequest
    context: dict[str, Any]
    analysis: GeneratedCostAnalysis
    result: dict[str, Any]


class PlanningCostGraph:
    def __init__(
        self,
        cost_service: PlanningCostService | None = None,
        llm_service: PlanningCostLLMService | None = None,
    ) -> None:
        self.cost_service = cost_service or PlanningCostService()
        self.llm_service = llm_service or PlanningCostLLMService()
        self.graph = self._build()

    def invoke(self, request: PlanningCostRequest) -> dict[str, Any]:
        return self.graph.invoke({"request": request})["result"]

    def _build(self):
        workflow = StateGraph(PlanningCostState)
        workflow.add_node("prepare_context", self._prepare_context)
        workflow.add_node("analyze_additional_costs", self._analyze_costs)
        workflow.add_node("calculate_estimate", self._calculate_estimate)

        workflow.add_edge(START, "prepare_context")
        workflow.add_edge("prepare_context", "analyze_additional_costs")
        workflow.add_edge("analyze_additional_costs", "calculate_estimate")
        workflow.add_edge("calculate_estimate", END)
        return workflow.compile()

    def _prepare_context(
        self,
        state: PlanningCostState,
    ) -> dict[str, Any]:
        return {
            "context": self.cost_service.prepare_context(state["request"])
        }

    def _analyze_costs(
        self,
        state: PlanningCostState,
    ) -> dict[str, Any]:
        return {
            "analysis": self.llm_service.generate(state["context"])
        }

    def _calculate_estimate(
        self,
        state: PlanningCostState,
    ) -> dict[str, Any]:
        return {
            "result": self.cost_service.calculate(
                state["request"],
                state["analysis"],
            )
        }
