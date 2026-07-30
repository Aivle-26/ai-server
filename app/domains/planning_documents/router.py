import asyncio
import json
import logging
import unicodedata
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from .document_parser import (
    DocumentExtractionError,
    MAX_FILE_COUNT,
    MAX_FILE_SIZE,
    UploadedDocument,
)
from .graph import PlanningDocumentGraph
from .readjustment import RequirementReadjustmentService
from .settings import PlanningAnalysisSettings
from .schemas import (
    DocumentManifestItem,
    ExistingRequirement,
    PlanningDocumentExtractionResponse,
    PlanningRequirementReadjustmentResponse,
)

router = APIRouter()
planning_document_graph = PlanningDocumentGraph()
readjustment_service = RequirementReadjustmentService()
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
    document_manifest: str | None = Form(
        default=None,
        description="files와 같은 순서의 document_id/file_name JSON 배열",
    ),
) -> dict:
    request_id = uuid4().hex
    started_at = perf_counter()
    if len(files) > MAX_FILE_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"문서는 최대 {MAX_FILE_COUNT}개까지 업로드할 수 있습니다.",
        )

    manifest = _parse_document_manifest(document_manifest, files)
    uploads = await _read_uploads(files, manifest)

    try:
        result = await _invoke_graph(
            uploads,
            request_id=request_id,
            started_at=started_at,
            max_analysis_inputs=_configured_limit(
                "planning_max_analysis_chunks"
            ),
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
        _log_timeout(request_id, len(uploads), started_at, "extract")
        raise _analysis_timeout_error() from exc
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/api/v1/planning/documents/readjust",
    response_model=PlanningRequirementReadjustmentResponse,
    summary="추가 문서를 기준으로 요구사항 변경 후보 생성",
)
async def readjust_planning_requirements(
    files: list[UploadFile] = File(...),
    existing_requirements: str = Form(
        ...,
        description="현재 요구사항 목록 JSON 배열",
    ),
    document_manifest: str | None = Form(
        default=None,
        description="files와 같은 순서의 document_id/file_name JSON 배열",
    ),
) -> dict:
    request_id = uuid4().hex
    started_at = perf_counter()
    if len(files) > MAX_FILE_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"문서는 최대 {MAX_FILE_COUNT}개까지 업로드할 수 있습니다.",
        )

    manifest = _parse_document_manifest(document_manifest, files)
    existing = _parse_existing_requirements(existing_requirements)
    uploads = await _read_uploads(files, manifest)
    try:
        extraction = await _invoke_graph(
            uploads,
            request_id=request_id,
            started_at=started_at,
            max_analysis_inputs=_configured_limit(
                "planning_readjust_max_analysis_chunks"
            ),
        )
        return {
            "change_candidates": readjustment_service.build_changes(
                existing,
                extraction.get("requirement_candidates") or [],
            ),
            "documents": extraction.get("documents") or [],
            "llm_status": extraction.get("llm_status") or "FALLBACK",
        }
    except TimeoutError as exc:
        _log_timeout(request_id, len(uploads), started_at, "readjust")
        raise _analysis_timeout_error() from exc
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _graph_settings() -> object:
    settings = getattr(planning_document_graph, "settings", None)
    if settings is not None:
        return settings
    return PlanningAnalysisSettings.from_env()


def _configured_limit(name: str) -> int:
    default_settings = PlanningAnalysisSettings.from_env()
    return int(getattr(_graph_settings(), name, getattr(default_settings, name)))


async def _invoke_graph(
    uploads: list[UploadedDocument],
    *,
    request_id: str,
    started_at: float,
    max_analysis_inputs: int,
) -> dict:
    settings = _graph_settings()
    deadline_monotonic = (
        started_at
        + float(
            getattr(
                settings,
                "planning_analysis_timeout_seconds",
                PlanningAnalysisSettings.from_env().planning_analysis_timeout_seconds,
            )
        )
    )
    remaining_timeout = deadline_monotonic - perf_counter()
    if remaining_timeout <= 0:
        raise TimeoutError("planning analysis deadline reached")

    invoke_kwargs: dict[str, object] = {"request_id": request_id}
    if isinstance(planning_document_graph, PlanningDocumentGraph):
        invoke_kwargs.update({
            "started_at": started_at,
            "deadline_monotonic": deadline_monotonic,
            "max_analysis_inputs": max_analysis_inputs,
        })
    return await asyncio.wait_for(
        asyncio.to_thread(
            planning_document_graph.invoke,
            uploads,
            **invoke_kwargs,
        ),
        timeout=remaining_timeout,
    )


def _analysis_timeout_error() -> HTTPException:
    return HTTPException(
        status_code=504,
        detail="문서 분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
    )


def _log_timeout(
    request_id: str,
    document_count: int,
    started_at: float,
    operation: str,
) -> None:
    logger.warning(
        "planning_extract_audit %s",
        json.dumps(
            {
                "event": "planning_analysis_timed_out",
                "operation": operation,
                "request_id": request_id,
                "document_count": document_count,
                "latency_ms": round((perf_counter() - started_at) * 1000),
                "timed_out": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _parse_document_manifest(
    raw_manifest: str | None,
    files: list[UploadFile],
) -> list[DocumentManifestItem | None]:
    if raw_manifest is None or not raw_manifest.strip():
        return [None] * len(files)
    try:
        payload = json.loads(raw_manifest)
        if not isinstance(payload, list):
            raise ValueError
        manifest = [
            DocumentManifestItem.model_validate(item)
            for item in payload
        ]
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="document_manifest must be a valid JSON array.",
        ) from exc

    if len(manifest) != len(files):
        raise HTTPException(
            status_code=422,
            detail="document_manifest count must match files count.",
        )
    document_ids = [item.document_id for item in manifest]
    if len(document_ids) != len(set(document_ids)):
        raise HTTPException(
            status_code=422,
            detail="document_manifest contains duplicate document_id values.",
        )
    for file, item in zip(files, manifest, strict=True):
        file_name = _normalize_file_name(file.filename or "unnamed")
        manifest_name = _normalize_file_name(item.file_name)
        if file_name != manifest_name:
            raise HTTPException(
                status_code=422,
                detail="document_manifest file_name must match files order.",
            )
    return manifest


def _parse_existing_requirements(raw_requirements: str) -> list[ExistingRequirement]:
    try:
        payload = json.loads(raw_requirements)
        if not isinstance(payload, list):
            raise ValueError
        requirements = [
            ExistingRequirement.model_validate(item)
            for item in payload
        ]
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="existing_requirements must be a valid JSON array.",
        ) from exc
    requirement_ids = [
        requirement.requirement_id for requirement in requirements
    ]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise HTTPException(
            status_code=422,
            detail="existing_requirements contains duplicate requirement_id values.",
        )
    return requirements


async def _read_uploads(
    files: list[UploadFile],
    manifest: list[DocumentManifestItem | None],
) -> list[UploadedDocument]:
    uploads = []
    for file, manifest_item in zip(files, manifest, strict=True):
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
                document_id=(
                    manifest_item.document_id
                    if manifest_item is not None
                    else None
                ),
            )
        )
    return uploads


def _normalize_file_name(file_name: str) -> str:
    normalized = unicodedata.normalize("NFC", file_name).replace("\\", "/")
    return Path(normalized).name
