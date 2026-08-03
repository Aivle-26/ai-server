from fastapi import APIRouter

from .graph import ReportGraph
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

router = APIRouter()
report_graph = ReportGraph()


@router.post(
    "/api/v1/reports/meeting/analyze",
    response_model=MeetingAnalysisResponse,
    summary="회의록 기반 보고 데이터 추출",
    description=(
        "회의록을 분석하여 회의 요약, 결정 로그, 액션 아이템, "
        "이슈 리스크 변경 후보를 추출합니다."
    ),
)
def analyze_meeting_report(
    request: MeetingAnalysisRequest,
) -> MeetingAnalysisResponse:
    return report_graph.analyze_meeting(request)


@router.post(
    "/api/v1/reports/weekly/generate",
    response_model=WeeklyReportResponse,
    summary="주간 스크럼 및 보고서 자동 생성",
    description=(
        "WBS 기준 일정, 완료된 액션 아이템, 진행 중 업무, 리스크 정보를 바탕으로 "
        "주간 보고서 초안을 생성합니다."
    ),
)
def generate_weekly_report(
    request: WeeklyReportRequest,
) -> WeeklyReportResponse:
    return report_graph.generate_weekly_report(request)


@router.post(
    "/api/v1/reports/final/generate",
    response_model=FinalReportResponse,
    summary="최종 보고서 자동 생성",
    description=(
        "승인된 보고서와 이행 결과, 산출물 정보를 바탕으로 "
        "프로젝트 최종 보고서 초안을 생성합니다."
    ),
)
def generate_final_report(
    request: FinalReportRequest,
) -> FinalReportResponse:
    return report_graph.generate_final_report(request)


@router.post(
    "/api/v1/reports/deliverables/rag/query",
    response_model=DeliverableRagResponse,
    summary="산출물 기반 RAG 챗봇 질의응답",
    description=(
        "요구사항 정의서, 회의록, 보고서, 산출물 등 프로젝트 문서를 근거로 "
        "사용자 질문에 답변합니다."
    ),
)
def query_deliverable_rag(
    request: DeliverableRagRequest,
) -> DeliverableRagResponse:
    return report_graph.query_deliverable_rag(request)


@router.post(
    "/api/v1/reports/weekly-scrum/summarize",
    response_model=WeeklyScrumSummarizeResponse,
    summary="팀원별 주간 스크럼 종합 요약",
)
def summarize_weekly_scrum(
    request: WeeklyScrumSummarizeRequest,
) -> WeeklyScrumSummarizeResponse:
    return report_graph.summarize_weekly_scrum(request)


@router.post(
    "/api/v1/reports/weekly-scrum/review",
    response_model=WeeklyScrumReviewResponse,
    summary="주간 스크럼 기준문서 기반 검토",
)
def review_weekly_scrum(
    request: WeeklyScrumReviewRequest,
) -> WeeklyScrumReviewResponse:
    return report_graph.review_weekly_scrum(request)


@router.post(
    "/api/v1/reports/weekly-scrum/recommend-next-actions",
    response_model=WeeklyScrumRecommendNextActionsResponse,
    summary="다음 주 실행 업무 추천",
)
def recommend_next_actions(
    request: WeeklyScrumRecommendNextActionsRequest,
) -> WeeklyScrumRecommendNextActionsResponse:
    return report_graph.recommend_next_actions(request)


@router.post(
    "/api/v1/reports/weekly-scrum/finalize",
    response_model=WeeklyScrumFinalizeResponse,
    summary="PM 검토 결과 기반 최종 주간 보고서 생성",
)
def finalize_weekly_scrum_report(
    request: WeeklyScrumFinalizeRequest,
) -> WeeklyScrumFinalizeResponse:
    return report_graph.finalize_weekly_scrum_report(request)
