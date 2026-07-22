from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.report import MeetingAnalysisRequest, MeetingAnalysisResponse
from app.services.report_llm_service import ReportLLMService
from app.services.report_service import ReportService


class ReportAgentState(TypedDict, total=False):
    request: MeetingAnalysisRequest
    llm_result: dict[str, Any]
    llm_status: str
    result: MeetingAnalysisResponse


class ReportGraph:
    def __init__(self) -> None:
        self.report_service = ReportService()
        self.llm_service = ReportLLMService()
        self.graph = self._build()

    def invoke(self, request: MeetingAnalysisRequest) -> MeetingAnalysisResponse:
        state = self.graph.invoke({"request": request})
        return state["result"]

    def _build(self):
        graph = StateGraph(ReportAgentState)

        graph.add_node("analyze_meeting", self._analyze_meeting)
        graph.add_node("build_response", self._build_response)

        graph.add_edge(START, "analyze_meeting")
        graph.add_edge("analyze_meeting", "build_response")
        graph.add_edge("build_response", END)

        return graph.compile()

    def _analyze_meeting(self, state: ReportAgentState) -> ReportAgentState:
        request = state["request"]

        llm_result, llm_status = self.llm_service.analyze_meeting(
            project_name=request.project_name,
            meeting_title=request.meeting_document.meeting_title,
            meeting_text=request.meeting_document.text,
            enabled=request.enable_llm,
        )

        return {
            "llm_result": llm_result,
            "llm_status": llm_status,
        }

    def _build_response(self, state: ReportAgentState) -> ReportAgentState:
        request = state["request"]
        llm_result = state["llm_result"]
        llm_status = state["llm_status"]

        result = self.report_service.build_meeting_response(
            request=request,
            llm_result=llm_result,
            llm_status=llm_status,
        )

        return {"result": result}