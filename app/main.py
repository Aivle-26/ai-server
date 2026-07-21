from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile

from app.agents.communication_risk_graph import CommunicationRiskGraph
from app.agents.planning_document_graph import PlanningDocumentGraph
from app.schemas.communication_risk import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
)
from app.schemas.planning_document import PlanningDocumentExtractionResponse
from app.services.planning_document_service import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)


app = FastAPI(
    title="AI Project Management Server",
    version="0.1.0",
)

communication_risk_graph = CommunicationRiskGraph()
planning_document_graph = PlanningDocumentGraph()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/risk/communication/analyze",
    response_model=CommunicationRiskResponse,
    summary="Analyze project Slack communication risk",
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
    summary="Extract project information and requirement candidates from planning documents",
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
