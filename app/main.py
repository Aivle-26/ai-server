from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.agents.communication_risk_graph import CommunicationRiskGraph
from app.agents.planning_document_graph import PlanningDocumentGraph
from app.agents.report_graph import ReportGraph
from app.schemas.communication_risk import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
)
from app.schemas.planning_document import PlanningDocumentExtractionResponse
from app.schemas.report import (
    DeliverableRagRequest,
    DeliverableRagResponse,
    FinalReportRequest,
    FinalReportResponse,
    MeetingAnalysisRequest,
    MeetingAnalysisResponse,
    WeeklyReportRequest,
    WeeklyReportResponse,
)
from app.services.planning_document_service import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)

from app.api.risk_router import router as risk_router

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


@app.post(
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


@app.post(
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


@app.post(
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
