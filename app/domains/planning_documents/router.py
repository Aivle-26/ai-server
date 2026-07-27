from fastapi import APIRouter, File, HTTPException, UploadFile

from .document_parser import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)
from .graph import PlanningDocumentGraph
from .schemas import PlanningDocumentExtractionResponse

router = APIRouter()
planning_document_graph = PlanningDocumentGraph()


@router.post(
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
