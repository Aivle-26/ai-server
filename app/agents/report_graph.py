from app.schemas.report import (
    WeeklyScrumFinalizeRequest,
    WeeklyScrumFinalizeResponse,
    WeeklyScrumRecommendNextActionsRequest,
    WeeklyScrumRecommendNextActionsResponse,
    WeeklyScrumReviewRequest,
    WeeklyScrumReviewResponse,
    WeeklyScrumSummarizeRequest,
    WeeklyScrumSummarizeResponse,
)
from app.services.report_service import ReportService


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