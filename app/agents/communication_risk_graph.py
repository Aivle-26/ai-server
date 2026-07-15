from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.communication_llm_decision_service import CommunicationLLMDecisionService
from app.services.communication_risk_service import CommunicationRiskService


class CommunicationRiskState(TypedDict, total=False):
    project_id: int
    project_name: str | None
    analysis_end: str
    messages: list[dict[str, Any]]
    enable_llm: bool
    facts: dict[str, Any]
    fallback_decision: dict[str, Any]
    decision: dict[str, Any]
    llm_status: str
    result: dict[str, Any]


class CommunicationRiskGraph:
    def __init__(
        self,
        risk_service: CommunicationRiskService | None = None,
        decision_service: CommunicationLLMDecisionService | None = None,
    ) -> None:
        self.risk_service = risk_service or CommunicationRiskService()
        self.decision_service = decision_service or CommunicationLLMDecisionService()
        self.graph = self._build()

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.graph.invoke(request)["result"]

    def _build(self):
        workflow = StateGraph(CommunicationRiskState)
        workflow.add_node("calculate_facts", self._calculate_facts)
        workflow.add_node("judge_risk_with_llm", self._judge_risk_with_llm)
        workflow.add_node("build_response", self._build_response)
        workflow.add_edge(START, "calculate_facts")
        workflow.add_edge("calculate_facts", "judge_risk_with_llm")
        workflow.add_edge("judge_risk_with_llm", "build_response")
        workflow.add_edge("build_response", END)
        return workflow.compile()

    def _calculate_facts(self, state: CommunicationRiskState) -> dict[str, Any]:
        facts = self.risk_service.build_facts(state["messages"], state["analysis_end"])
        return {"facts": facts, "fallback_decision": self.risk_service.fallback_decision(facts)}

    def _judge_risk_with_llm(self, state: CommunicationRiskState) -> dict[str, Any]:
        decision, status = self.decision_service.decide(
            facts=state["facts"],
            project_name=state.get("project_name"),
            enabled=state.get("enable_llm", True),
            fallback=state["fallback_decision"],
        )
        return {"decision": decision, "llm_status": status}

    def _build_response(self, state: CommunicationRiskState) -> dict[str, Any]:
        return {"result": self.risk_service.build_response(
            project_id=state["project_id"],
            project_name=state.get("project_name"),
            facts=state["facts"],
            decision=state["decision"],
            llm_status=state["llm_status"],
        )}
