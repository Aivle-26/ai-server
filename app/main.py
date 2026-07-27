from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.agents.communication_risk_graph import CommunicationRiskGraph
from app.agents.planning_document_graph import PlanningDocumentGraph
from app.agents.planning_resource_graph import PlanningResourceGraph
from app.agents.planning_schedule_graph import PlanningScheduleGraph
from app.agents.planning_wbs_graph import PlanningWBSGraph
from app.schemas.communication_risk import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
)
from app.schemas.planning_document import PlanningDocumentExtractionResponse
from app.schemas.planning_resource import (
    PlanningResourceRequest,
    PlanningResourceResponse,
)
from app.schemas.planning_schedule import (
    PlanningScheduleRequest,
    PlanningScheduleResponse,
)
from app.schemas.planning_wbs import WBSGenerationRequest, WBSGenerationResponse
from app.services.planning_document_service import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)
from app.services.planning_resource_llm_service import (
    ResourceLLMConfigurationError,
    ResourceLLMGenerationError,
)
from app.services.planning_wbs_llm_service import (
    WBSLLMConfigurationError,
    WBSLLMGenerationError,
)
from app.services.planning_schedule_llm_service import (
    ScheduleLLMConfigurationError,
    ScheduleLLMGenerationError,
)


app = FastAPI(
    title="AI 프로젝트 관리 서버",
    version="0.1.0",
)

communication_risk_graph = CommunicationRiskGraph()
planning_document_graph = PlanningDocumentGraph()
planning_wbs_graph = PlanningWBSGraph()
planning_schedule_graph = PlanningScheduleGraph()
planning_resource_graph = PlanningResourceGraph()


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
        raise HTTPException(status_code=422, detail=f"문서는 최대 {MAX_FILE_COUNT}개까지 업로드할 수 있습니다.")
    uploads = []
    for file in files:
        content = await file.read(MAX_FILE_SIZE + 1)
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"파일 크기는 20MB를 초과할 수 없습니다: {file.filename}")
        uploads.append(UploadedDocument(
            file_name=file.filename or "unnamed",
            content_type=file.content_type,
            content=content,
        ))
    try:
        return planning_document_graph.invoke(uploads)
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/v1/planning/wbs/generate",
    response_model=WBSGenerationResponse,
    summary="프로젝트 WBS 작업분해구조 생성",
    description=(
        "프로젝트 기본정보와 요구사항을 바탕으로 일정·담당자를 제외한 "
        "PHASE, WORK_PACKAGE, TASK 3단계 WBS를 생성합니다."
    ),
)
def generate_planning_wbs(request: WBSGenerationRequest) -> dict:
    try:
        return planning_wbs_graph.invoke(request)
    except WBSLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WBSLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post(
    "/api/v1/planning/schedules/recommend",
    response_model=PlanningScheduleResponse,
    summary="WBS 기반 프로젝트 일정 추천",
    description=(
        "WBS 작업을 바탕으로 Monte Carlo 방식을 적용하여 각 WBS의 "
        "예상·권장·보수적 시작일과 종료일을 반환합니다."
    ),
)
def recommend_planning_schedule(request: PlanningScheduleRequest) -> dict:
    try:
        return planning_schedule_graph.invoke(request)
    except ScheduleLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ScheduleLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post(
    "/api/v1/planning/resources/recommend",
    response_model=PlanningResourceResponse,
    summary="프로젝트 필요 인력·담당자·MM 추천",
    description=(
        "선택된 WBS TASK 일정과 프로젝트 참여자의 역할·기술·숙련도·경력·"
        "주간 가용시간을 바탕으로 TASK별 공수와 MM, 역할별 필요 인력 및 "
        "추천 담당자를 반환합니다."
    ),
)
def recommend_planning_resources(request: PlanningResourceRequest) -> dict:
    try:
        return planning_resource_graph.invoke(request)
    except ResourceLLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ResourceLLMGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
