from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .llm_service import (
    GeneratedWBSPlan,
    PlanningWBSLLMService,
    WBSLLMConfigurationError,
    WBSLLMGenerationError,
)
from .schemas import WBSGenerationRequest
from .service import PlanningWBSService, WBSBuildOutcome


class PlanningWBSState(TypedDict, total=False):
    request: WBSGenerationRequest
    contexts: list[dict[str, Any]]
    plans: list[GeneratedWBSPlan]
    outcome: WBSBuildOutcome
    repair_warnings: list[str]
    result: dict[str, Any]


class PlanningWBSGraph:
    def __init__(
        self,
        wbs_service: PlanningWBSService | None = None,
        llm_service: PlanningWBSLLMService | None = None,
    ) -> None:
        self.wbs_service = wbs_service or PlanningWBSService()
        self.llm_service = llm_service or PlanningWBSLLMService()
        self.graph = self._build()

    def invoke(self, request: WBSGenerationRequest) -> dict[str, Any]:
        return self.graph.invoke({"request": request})["result"]

    def _build(self):
        workflow = StateGraph(PlanningWBSState)
        workflow.add_node("prepare_context", self._prepare_context)
        workflow.add_node("generate_wbs", self._generate_wbs)
        workflow.add_node("finalize_initial", self._finalize_initial)
        workflow.add_node("repair_gaps", self._repair_gaps)
        workflow.add_node("finalize_repaired", self._finalize_repaired)
        workflow.add_node("build_response", self._build_response)

        workflow.add_edge(START, "prepare_context")
        workflow.add_edge("prepare_context", "generate_wbs")
        workflow.add_edge("generate_wbs", "finalize_initial")
        workflow.add_conditional_edges(
            "finalize_initial",
            self._route_after_initial,
            {"repair": "repair_gaps", "complete": "build_response"},
        )
        workflow.add_edge("repair_gaps", "finalize_repaired")
        workflow.add_edge("finalize_repaired", "build_response")
        workflow.add_edge("build_response", END)
        return workflow.compile()

    def _prepare_context(self, state: PlanningWBSState) -> dict[str, Any]:
        return {
            "contexts": self.wbs_service.prepare_contexts(state["request"]),
        }

    def _generate_wbs(self, state: PlanningWBSState) -> dict[str, Any]:
        return {"plans": self.llm_service.generate(state["contexts"])}

    def _finalize_initial(self, state: PlanningWBSState) -> dict[str, Any]:
        return {
            "outcome": self.wbs_service.finalize(state["request"], state["plans"]),
        }

    def _route_after_initial(self, state: PlanningWBSState) -> str:
        return "repair" if state["outcome"].needs_repair else "complete"

    def _repair_gaps(self, state: PlanningWBSState) -> dict[str, Any]:
        outcome = state["outcome"]
        contexts = self.wbs_service.prepare_contexts(
            state["request"],
            target_requirement_ids=outcome.missing_requirement_ids,
            target_artifact_types=outcome.missing_artifact_types,
            target_phase_names=outcome.missing_phase_names,
        )
        try:
            repair_plans = self.llm_service.generate(contexts)
            return {"plans": [*state["plans"], *repair_plans], "repair_warnings": []}
        except (WBSLLMConfigurationError, WBSLLMGenerationError) as exc:
            return {
                "repair_warnings": [f"누락 항목 자동 보완에 실패했습니다: {exc}"],
            }

    def _finalize_repaired(self, state: PlanningWBSState) -> dict[str, Any]:
        return {
            "outcome": self.wbs_service.finalize(
                state["request"],
                state["plans"],
                state.get("repair_warnings", []),
            ),
        }

    def _build_response(self, state: PlanningWBSState) -> dict[str, Any]:
        return {
            "result": {
                **state["outcome"].result,
                "llm_status": "SUCCEEDED",
            }
        }
