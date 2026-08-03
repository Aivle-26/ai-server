from fastapi import FastAPI, File, HTTPException, UploadFile

from app.domains.planning_documents.schemas import (
    PlanningDocumentExtractionResponse,
)
from tests.e2e_stub.fixtures import planning_document_response


app = FastAPI(
    title="AIPM Planning Document E2E Stub",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "planning-document-e2e-stub"}


@app.post(
    "/api/v1/planning/documents/extract",
    response_model=PlanningDocumentExtractionResponse,
)
async def extract_planning_documents(
    files: list[UploadFile] = File(...),
) -> PlanningDocumentExtractionResponse:
    uploads: list[tuple[str, bytes]] = []
    for file in files:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=422,
                detail="E2E stub does not accept empty files.",
            )
        uploads.append((file.filename or "unnamed", content))

    return planning_document_response(uploads)
