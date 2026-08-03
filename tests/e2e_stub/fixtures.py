from datetime import date
from pathlib import Path

from app.domains.planning_documents.schemas import (
    ParsedDocumentInfo,
    PlanningDocumentExtractionResponse,
    ProjectBasicInfo,
    RequiredArtifact,
    RequirementCandidate,
)


STUB_MARKER = "E2E-PLANNING-STUB-V1"


def planning_document_response(
    uploaded_files: list[tuple[str, bytes]],
) -> PlanningDocumentExtractionResponse:
    source_document = uploaded_files[0][0]
    documents = [
        ParsedDocumentInfo(
            file_name=file_name,
            file_type=_file_type(file_name),
            character_count=len(content.decode("utf-8", errors="replace")),
            processing_mode="TEXT",
        )
        for file_name, content in uploaded_files
    ]

    return PlanningDocumentExtractionResponse(
        project_info=ProjectBasicInfo(
            project_name=f"{STUB_MARKER} Project",
            project_goal="Validate the persisted requirement analysis flow.",
            client_organization="AIPM E2E",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 12, 31),
            key_features=[
                "User login",
                "Project document upload",
                "Requirement review and confirmation",
            ],
            required_artifacts=[
                RequiredArtifact(
                    artifact_type="REQUIREMENTS_DEFINITION",
                    artifact_name="Requirements Definition",
                    required_version="1.0",
                )
            ],
            acceptance_conditions=[
                f"{STUB_MARKER}: exactly three requirements are persisted."
            ],
        ),
        requirement_candidates=[
            RequirementCandidate(
                requirement_id=91001,
                function_name=f"{STUB_MARKER} User Login",
                requirement_text="A registered user can sign in securely.",
                category="FUNCTIONAL",
                priority="HIGH",
                acceptance_criteria="A valid user receives an authenticated session.",
                source_document=source_document,
                source_excerpt=f"{STUB_MARKER}: user login",
            ),
            RequirementCandidate(
                requirement_id=91002,
                function_name=f"{STUB_MARKER} Project Document Upload",
                requirement_text="A project manager can upload a project source document.",
                category="FUNCTIONAL",
                priority="HIGH",
                acceptance_criteria="The document is stored and listed for the same project.",
                source_document=source_document,
                source_excerpt=f"{STUB_MARKER}: project document upload",
            ),
            RequirementCandidate(
                requirement_id=91003,
                function_name=f"{STUB_MARKER} Requirement Review",
                requirement_text="A project manager can review and confirm extracted requirements.",
                category="PROJECT_MANAGEMENT",
                priority="MEDIUM",
                acceptance_criteria="The reviewed requirement can be confirmed.",
                source_document=source_document,
                source_excerpt=f"{STUB_MARKER}: requirement review and confirmation",
            ),
        ],
        documents=documents,
        llm_status="SUCCEEDED",
    )


def _file_type(file_name: str) -> str:
    suffix = Path(file_name).suffix.lstrip(".").upper()
    return suffix or "UNKNOWN"
