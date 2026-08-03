from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from app.agents.communication_risk_graph import CommunicationRiskGraph
from app.agents.planning_document_graph import PlanningDocumentGraph
from app.agents.report_graph import ReportGraph
from app.api.risk_router import router as risk_router
from app.schemas.communication_risk import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
)
from app.schemas.planning_document import PlanningDocumentExtractionResponse
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
from app.services.planning_document_service import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)

app = FastAPI(
    title="AI Project Data Platform",
    version="0.1.0",
)

app.include_router(risk_router)

communication_risk_graph = CommunicationRiskGraph()
planning_document_graph = PlanningDocumentGraph()
report_graph = ReportGraph()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/risk/communication/analyze",
    response_model=CommunicationRiskResponse,
    summary="프로젝트 커뮤니케이션 위험 분석",
    description="프로젝트의 Slack 메시지를 분석하여 커뮤니케이션 위험도와 판단 근거를 반환합니다.",
)
def analyze_communication_risk(
    request: CommunicationRiskRequest,
) -> dict:
    analysis_end = request.analysis_end or datetime.now(timezone.utc)
    payload = request.model_dump(mode="json")
    payload["analysis_end"] = analysis_end.isoformat()
    return communication_risk_graph.invoke(payload)


@app.post(
    "/api/v1/planning/documents/extract",
    response_model=PlanningDocumentExtractionResponse,
    summary="프로젝트 초기 문서 정보 및 요구사항 추출",
    description=(
        "기획서, 제안서, RFP 등 프로젝트 초기 문서에서 기본정보, 필수 산출물과 "
        "요구사항 후보를 추출합니다."
    ),
)
async def extract_planning_documents(
    files: list[UploadFile] = File(
        ...,
        description="분석할 프로젝트 기획 문서 목록",
        json_schema_extra={
            "items": {"type": "string", "format": "binary"},
        },
    ),
) -> dict:
    if len(files) > MAX_FILE_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"문서는 최대 {MAX_FILE_COUNT}개까지 업로드할 수 있습니다.",
        )

    uploads = []
    for file in files:
        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"파일 크기는 20MB를 초과할 수 없습니다: {file.filename}",
            )

        uploads.append(
            UploadedDocument(
                file_name=file.filename or "unnamed",
                content_type=file.content_type,
                content=content,
            )
        )

    try:
        return planning_document_graph.invoke(uploads)
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/v1/reports/weekly-scrum/summarize",
    response_model=WeeklyScrumSummarizeResponse,
    summary="팀원별 주간 스크럼 종합 요약",
    description=(
        "팀원별 주간 스크럼을 사실 기반으로 통합하고, "
        "LLM을 이용해 팀 전체 종합 요약을 생성합니다."
    ),
)
def summarize_weekly_scrum(
    request: WeeklyScrumSummarizeRequest,
) -> WeeklyScrumSummarizeResponse:
    return report_graph.summarize_weekly_scrum(request)


@app.post(
    "/api/v1/reports/weekly-scrum/review",
    response_model=WeeklyScrumReviewResponse,
    summary="주간 스크럼 기준문서 기반 검토",
    description=(
        "종합 요약과 기준문서를 바탕으로 누락, 모순, 위험, "
        "의존성, 보강 필요 항목을 검토 후보로 생성합니다."
    ),
)
def review_weekly_scrum(
    request: WeeklyScrumReviewRequest,
) -> WeeklyScrumReviewResponse:
    return report_graph.review_weekly_scrum(request)


@app.post(
    "/api/v1/reports/weekly-scrum/recommend-next-actions",
    response_model=WeeklyScrumRecommendNextActionsResponse,
    summary="다음 주 실행 업무 추천",
    description=(
        "검토 결과를 바탕으로 다음 주 업무, 담당자, 기한, "
        "우선순위, 완료 조건 후보를 추천합니다."
    ),
)
def recommend_next_actions(
    request: WeeklyScrumRecommendNextActionsRequest,
) -> WeeklyScrumRecommendNextActionsResponse:
    return report_graph.recommend_next_actions(request)


@app.post(
    "/api/v1/reports/weekly-scrum/finalize",
    response_model=WeeklyScrumFinalizeResponse,
    summary="PM 검토 결과 기반 최종 주간 보고서 생성",
    description=(
        "PM이 승인, 수정 또는 거절한 검토 후보와 실행계획을 반영하여 "
        "최종 주간 프로젝트 상태 보고서를 생성합니다."
    ),
)
def finalize_weekly_scrum_report(
    request: WeeklyScrumFinalizeRequest,
) -> WeeklyScrumFinalizeResponse:
    return report_graph.finalize_weekly_scrum_report(request)