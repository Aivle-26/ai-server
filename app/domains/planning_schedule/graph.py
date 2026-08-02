from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .llm_service import (
    GeneratedSchedulePlan,
    PlanningScheduleLLMService,
)
from .schemas import PlanningScheduleRequest
from .service import PlanningScheduleService


class PlanningScheduleState(TypedDict, total=False):
    request: PlanningScheduleRequest
    context: dict[str, Any]
    plan: GeneratedSchedulePlan
    result: dict[str, Any]


class PlanningScheduleGraph:
    def __init__(
        self,
        schedule_service: PlanningScheduleService | None = None,
        llm_service: PlanningScheduleLLMService | None = None,
    ) -> None:
        self.schedule_service = schedule_service or PlanningScheduleService()
        self.llm_service = llm_service or PlanningScheduleLLMService()
        self.graph = self._build()

    def invoke(self, request: PlanningScheduleRequest) -> dict[str, Any]:
        return self.graph.invoke({"request": request})["result"]

    def _build(self):
        workflow = StateGraph(PlanningScheduleState)
        workflow.add_node("prepare_context", self._prepare_context)
        workflow.add_node("estimate_task_schedule", self._estimate_task_schedule)
        workflow.add_node("calculate_schedule", self._calculate_schedule)

        workflow.add_edge(START, "prepare_context")
        workflow.add_edge("prepare_context", "estimate_task_schedule")
        workflow.add_edge("estimate_task_schedule", "calculate_schedule")
        workflow.add_edge("calculate_schedule", END)
        return workflow.compile()

    def _prepare_context(self, state: PlanningScheduleState) -> dict[str, Any]:
        return {
            "context": self.schedule_service.prepare_context(state["request"]),
        }

    def _estimate_task_schedule(
        self,
        state: PlanningScheduleState,
    ) -> dict[str, Any]:
        return {"plan": self.llm_service.generate(state["context"])}

    def _calculate_schedule(
        self,
        state: PlanningScheduleState,
    ) -> dict[str, Any]:
        return {
            "result": {
                **self.schedule_service.build_schedule(
                state["request"],
                state["plan"],
                ),
                "llm_status": "SUCCEEDED",
            }
        }
