import asyncio
import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from .document_parser import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)
from .graph import PlanningDocumentGraph
from .schemas import PlanningDocumentExtractionResponse
from .settings import PlanningAnalysisSettings

router = APIRouter()
planning_document_graph = PlanningDocumentGraph()
logger = logging.getLogger("uvicorn.error")


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
    request_id = uuid4().hex
    started_at = perf_counter()
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
        graph_settings = getattr(
            planning_document_graph,
            "settings",
            None,
        ) or PlanningAnalysisSettings.from_env()
        deadline_monotonic = (
            started_at
            + graph_settings.planning_analysis_timeout_seconds
        )
        remaining_timeout = deadline_monotonic - perf_counter()
        if remaining_timeout <= 0:
            raise TimeoutError("planning analysis deadline reached")
        invoke_kwargs = {"request_id": request_id}
        if isinstance(planning_document_graph, PlanningDocumentGraph):
            invoke_kwargs.update({
                "started_at": started_at,
                "deadline_monotonic": deadline_monotonic,
            })
        result = await asyncio.wait_for(
            asyncio.to_thread(
                planning_document_graph.invoke,
                uploads,
                **invoke_kwargs,
            ),
            timeout=remaining_timeout,
        )
        logger.info(
            "planning_extract_audit %s",
            json.dumps(
                {
                    "event": "planning_extract_completed",
                    "request_id": request_id,
                    "llm_status": result.get("llm_status"),
                    "document_count": len(uploads),
                    "latency_ms": round(
                        (perf_counter() - started_at) * 1000
                    ),
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        return result
    except TimeoutError as exc:
        logger.warning(
            "planning_extract_audit %s",
            json.dumps(
                {
                    "event": "planning_extract_timed_out",
                    "request_id": request_id,
                    "document_count": len(uploads),
                    "latency_ms": round(
                        (perf_counter() - started_at) * 1000
                    ),
                    "timed_out": True,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        raise HTTPException(
            status_code=504,
            detail=(
                "문서 분석 시간이 초과되었습니다. "
                "잠시 후 다시 시도해 주세요."
            ),
        ) from exc
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
