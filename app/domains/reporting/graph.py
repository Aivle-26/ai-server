from .schemas import (
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from .service import ReportService


class ReportGraph:
    def __init__(self) -> None:
        self.report_service = ReportService()

    def invoke(self, request: MeetingAnalysisRequest) -> MeetingAnalysisResponse:
        return self.analyze_meeting(request)

    def analyze_meeting(self, request: MeetingAnalysisRequest) -> MeetingAnalysisResponse:
        return self.report_service.analyze_meeting(request)

    def generate_weekly_report(self, request: WeeklyReportRequest) -> WeeklyReportResponse:
        return self.report_service.generate_weekly_report(request)

    def generate_final_report(self, request: FinalReportRequest) -> FinalReportResponse:
        return self.report_service.generate_final_report(request)

    def answer_deliverable_rag(self, request: DeliverableRagRequest) -> DeliverableRagResponse:
        return self.report_service.answer_deliverable_rag(request)

    def query_deliverable_rag(self, request: DeliverableRagRequest) -> DeliverableRagResponse:
        return self.answer_deliverable_rag(request)
