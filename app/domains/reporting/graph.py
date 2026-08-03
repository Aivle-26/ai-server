from .schemas import (
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    WeeklyReportRequest,
    WeeklyReportResponse,
    WeeklyScrumFinalizeRequest,
    WeeklyScrumFinalizeResponse,
    WeeklyScrumRecommendNextActionsRequest,
    WeeklyScrumRecommendNextActionsResponse,
    WeeklyScrumReviewRequest,
    WeeklyScrumReviewResponse,
    WeeklyScrumSummarizeRequest,
    WeeklyScrumSummarizeResponse,
)
from .service import ReportService


class ReportGraph:
    def __init__(self) -> None:
        self.report_service = ReportService()

    def summarize_weekly_scrum(
        self,
        request: WeeklyScrumSummarizeRequest,
    ) -> WeeklyScrumSummarizeResponse:
        return self.report_service.summarize_weekly_scrum(request)

    def review_weekly_scrum(
        self,
        request: WeeklyScrumReviewRequest,
    ) -> WeeklyScrumReviewResponse:
        return self.report_service.review_weekly_scrum(request)

    def recommend_next_actions(
        self,
        request: WeeklyScrumRecommendNextActionsRequest,
    ) -> WeeklyScrumRecommendNextActionsResponse:
        return self.report_service.recommend_next_actions(request)

    def finalize_weekly_scrum_report(
        self,
        request: WeeklyScrumFinalizeRequest,
    ) -> WeeklyScrumFinalizeResponse:
        return self.report_service.finalize_weekly_scrum_report(request)

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

