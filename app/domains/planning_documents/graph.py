from __future__ import annotations

import logging
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .document_parser import PlanningDocumentService, UploadedDocument
from .llm_service import PlanningLLMExtractionService
from .quality import (
    RequirementQualityValidator,
    RequirementSentenceNormalizer,
    RequirementValidationIssue,
)


logger = logging.getLogger(__name__)


class PlanningDocumentState(TypedDict, total=False):
    uploads: list[UploadedDocument]
    documents: list[Any]
    chunks: list[dict[str, Any]]
    vision_documents: list[Any]
    fallback_extractions: list[dict[str, Any]]
    partial_extractions: list[dict[str, Any]]
    llm_status: str
    consolidated: dict[str, Any]
    quality_issues: list[RequirementValidationIssue]
    repair_succeeded: bool
    kept_original_ids: list[int]
    result: dict[str, Any]


class PlanningDocumentGraph:
    def __init__(
        self,
        document_service: PlanningDocumentService | None = None,
        llm_service: PlanningLLMExtractionService | None = None,
        quality_validator: RequirementQualityValidator | None = None,
        sentence_normalizer: RequirementSentenceNormalizer | None = None,
    ) -> None:
        self.document_service = document_service or PlanningDocumentService()
        self.llm_service = llm_service or PlanningLLMExtractionService()
        self.quality_validator = quality_validator or RequirementQualityValidator()
        self.sentence_normalizer = sentence_normalizer or RequirementSentenceNormalizer()
        self.graph = self._build()

    def invoke(self, uploads: list[UploadedDocument]) -> dict[str, Any]:
        started_at = time.perf_counter()
        result = self.graph.invoke({"uploads": uploads})["result"]
        logger.info(
            "프로젝트 문서 분석 완료: files=%s, requirements=%s, llm_status=%s, "
            "elapsed_seconds=%.3f",
            len(uploads),
            len(result["requirement_candidates"]),
            result["llm_status"],
            time.perf_counter() - started_at,
        )
        return result

    def _build(self):
        workflow = StateGraph(PlanningDocumentState)
        workflow.add_node("parse_documents", self._parse_documents)
        workflow.add_node("split_documents", self._split_documents)
        workflow.add_node("extract_with_llm", self._extract_with_llm)
        workflow.add_node("consolidate_results", self._consolidate_results)
        workflow.add_node("validate_requirements", self._validate_requirements)
        workflow.add_node("repair_invalid_requirements", self._repair_invalid_requirements)
        workflow.add_node("revalidate_requirements", self._revalidate_requirements)
        workflow.add_node("normalize_requirements", self._normalize_requirements)
        workflow.add_node("build_response", self._build_response)
        workflow.add_edge(START, "parse_documents")
        workflow.add_edge("parse_documents", "split_documents")
        workflow.add_edge("split_documents", "extract_with_llm")
        workflow.add_edge("extract_with_llm", "consolidate_results")
        workflow.add_edge("consolidate_results", "validate_requirements")
        workflow.add_conditional_edges(
            "validate_requirements",
            self._route_after_validation,
            {
                "repair": "repair_invalid_requirements",
                "normalize": "normalize_requirements",
            },
        )
        workflow.add_edge("repair_invalid_requirements", "revalidate_requirements")
        workflow.add_edge("revalidate_requirements", "normalize_requirements")
        workflow.add_edge("normalize_requirements", "build_response")
        workflow.add_edge("build_response", END)
        return workflow.compile()

    def _parse_documents(self, state: PlanningDocumentState) -> dict[str, Any]:
        return {"documents": self.document_service.parse_documents(state["uploads"])}

    def _split_documents(self, state: PlanningDocumentState) -> dict[str, Any]:
        chunks = self.document_service.build_chunks(state["documents"])
        logger.info(
            "문서 분할 완료: documents=%s, chunks=%s, blocks=%s, characters=%s",
            len(state["documents"]),
            len(chunks),
            sum(len(chunk.get("blocks") or []) for chunk in chunks),
            sum(len(document.text) for document in state["documents"]),
        )
        return {
            "chunks": chunks,
            "vision_documents": [
                document for document in state["documents"]
                if document.processing_mode == "PDF_VISION"
            ],
            "fallback_extractions": [self.document_service.fallback_extract(chunk) for chunk in chunks],
        }

    def _extract_with_llm(self, state: PlanningDocumentState) -> dict[str, Any]:
        partials, status = self.llm_service.extract(
            chunks=state["chunks"],
            vision_documents=state["vision_documents"],
            fallback_extractions=state["fallback_extractions"],
        )
        return {"partial_extractions": partials, "llm_status": status}

    def _consolidate_results(self, state: PlanningDocumentState) -> dict[str, Any]:
        return {"consolidated": self.document_service.consolidate(state["partial_extractions"])}

    def _validate_requirements(self, state: PlanningDocumentState) -> dict[str, Any]:
        issues = self.quality_validator.validate(
            state["consolidated"]["requirement_candidates"],
            self._source_texts(state),
        )
        error_count = sum(bool(issue.errors) for issue in issues)
        warning_count = sum(len(issue.warnings) for issue in issues)
        logger.info(
            "요구사항 품질 검증 완료: total=%s, invalid=%s, warnings=%s",
            len(state["consolidated"]["requirement_candidates"]),
            error_count,
            warning_count,
        )
        for issue in issues:
            if issue.errors or issue.warnings:
                logger.info(
                    "요구사항 검증 상세: requirement_id=%s, errors=%s, warnings=%s",
                    issue.requirement_id,
                    list(issue.errors),
                    list(issue.warnings),
                )
        return {"quality_issues": issues}

    def _route_after_validation(self, state: PlanningDocumentState) -> str:
        can_repair = callable(getattr(self.llm_service, "repair_requirements", None))
        if (
            any(issue.errors for issue in state.get("quality_issues") or [])
            and state.get("llm_status") != "SKIPPED_NO_API_KEY"
            and can_repair
        ):
            return "repair"
        return "normalize"

    def _repair_invalid_requirements(self, state: PlanningDocumentState) -> dict[str, Any]:
        issue_map = {
            issue.requirement_id: list(issue.errors)
            for issue in state["quality_issues"]
            if issue.errors
        }
        invalid_ids = set(issue_map)
        candidates = state["consolidated"]["requirement_candidates"]
        invalid_candidates = [
            candidate for candidate in candidates
            if candidate["requirement_id"] in invalid_ids
        ]
        repaired, succeeded = self.llm_service.repair_requirements(
            requirements=invalid_candidates,
            validation_errors=issue_map,
            source_texts=self._source_texts(state),
        )
        if not succeeded:
            logger.warning(
                "요구사항 선택 재생성 실패로 기존 결과 유지: count=%s",
                len(invalid_candidates),
            )
            return {"repair_succeeded": False, "llm_status": "FALLBACK"}

        repaired_by_original: dict[int, list[dict[str, Any]]] = {}
        for requirement in repaired:
            repaired_requirement = dict(requirement)
            original_id = int(repaired_requirement.pop("original_requirement_id"))
            repaired_by_original.setdefault(original_id, []).append(repaired_requirement)

        updated_candidates: list[dict[str, Any]] = []
        kept_original_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_id = int(candidate["requirement_id"])
            if candidate_id not in invalid_ids:
                updated_candidates.append(candidate)
                continue
            replacements = repaired_by_original.get(candidate_id, [])
            replacement_issues = self._validate_replacements(
                replacements,
                state,
            )
            replacement_has_errors = any(
                issue.errors for issue in replacement_issues
            )
            if replacements and not replacement_has_errors:
                updated_candidates.extend(replacements)
            else:
                updated_candidates.append(candidate)
                kept_original_candidates.append(candidate)
        self._renumber(updated_candidates)
        kept_original_ids = [
            int(candidate["requirement_id"])
            for candidate in updated_candidates
            if candidate in kept_original_candidates
        ]
        logger.info(
            "요구사항 선택 재생성 반영: invalid=%s, regenerated=%s, kept_original=%s",
            len(invalid_candidates),
            len(repaired),
            len(kept_original_ids),
        )
        return {
            "consolidated": {
                **state["consolidated"],
                "requirement_candidates": updated_candidates,
            },
            "repair_succeeded": True,
            "kept_original_ids": kept_original_ids,
            "llm_status": "FALLBACK" if kept_original_ids else state["llm_status"],
        }

    def _revalidate_requirements(self, state: PlanningDocumentState) -> dict[str, Any]:
        if not state.get("repair_succeeded"):
            return {}

        candidates = state["consolidated"]["requirement_candidates"]
        kept_original_ids = set(state.get("kept_original_ids") or [])
        candidates_to_validate = [
            candidate for candidate in candidates
            if candidate["requirement_id"] not in kept_original_ids
        ]
        issues = self.quality_validator.validate(
            candidates_to_validate,
            self._source_texts(state),
        )
        error_issues = [issue for issue in issues if issue.errors]
        if not error_issues:
            return {"quality_issues": issues}

        rejected_ids = {issue.requirement_id for issue in error_issues}
        logger.warning(
            "재검증 실패 요구사항이 있어 기존 결과를 유지합니다: count=%s, ids=%s",
            len(rejected_ids),
            sorted(rejected_ids),
        )
        return {
            "quality_issues": error_issues,
            "llm_status": "FALLBACK",
        }

    def _validate_replacements(
        self,
        replacements: list[dict[str, Any]],
        state: PlanningDocumentState,
    ) -> list[RequirementValidationIssue]:
        candidates = []
        for index, replacement in enumerate(replacements, start=1):
            candidate = dict(replacement)
            candidate["requirement_id"] = index
            candidates.append(candidate)
        return self.quality_validator.validate(candidates, self._source_texts(state))

    def _normalize_requirements(self, state: PlanningDocumentState) -> dict[str, Any]:
        candidates = self.sentence_normalizer.normalize(
            state["consolidated"]["requirement_candidates"]
        )
        self._renumber(candidates)
        return {
            "consolidated": {
                **state["consolidated"],
                "requirement_candidates": candidates,
            }
        }

    def _source_texts(self, state: PlanningDocumentState) -> dict[str, str]:
        return {
            document.file_name: document.text
            for document in state["documents"]
        }

    def _renumber(self, requirements: list[dict[str, Any]]) -> None:
        for index, requirement in enumerate(requirements, start=1):
            requirement["requirement_id"] = index

    def _build_response(self, state: PlanningDocumentState) -> dict[str, Any]:
        return {"result": {
            **state["consolidated"],
            "documents": [
                {
                    "file_name": document.file_name,
                    "file_type": document.file_type,
                    "character_count": len(document.text),
                    "processing_mode": document.processing_mode,
                }
                for document in state["documents"]
            ],
            "llm_status": state["llm_status"],
        }}
