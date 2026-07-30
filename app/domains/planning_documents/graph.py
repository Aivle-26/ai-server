from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .chunk_selector import AnalysisCandidate, select_analysis_inputs
from .document_parser import PlanningDocumentService, UploadedDocument
from .llm_service import (
    PlanningLLMExtractionOutcome,
    PlanningLLMExtractionService,
)
from .settings import PlanningAnalysisSettings


logger = logging.getLogger("uvicorn.error")


class PlanningDocumentState(TypedDict, total=False):
    request_id: str
    started_at: float
    deadline_monotonic: float
    max_analysis_inputs: int
    uploads: list[UploadedDocument]
    documents: list[Any]
    chunks: list[dict[str, Any]]
    vision_documents: list[Any]
    fallback_extractions: list[dict[str, Any]]
    selected_chunk_indices: list[int]
    selected_vision_document_indices: list[int]
    selected_chunks: list[dict[str, Any]]
    selected_vision_documents: list[Any]
    selected_fallback_extractions: list[dict[str, Any]]
    selected_inputs: list[dict[str, Any]]
    partial_extractions: list[dict[str, Any]]
    llm_status: str
    llm_call_count: int
    timed_out: bool
    fallback_used: bool
    consolidated: dict[str, Any]
    result: dict[str, Any]


class PlanningDocumentGraph:
    def __init__(
        self,
        document_service: PlanningDocumentService | None = None,
        llm_service: PlanningLLMExtractionService | None = None,
        settings: PlanningAnalysisSettings | None = None,
    ) -> None:
        self.document_service = document_service or PlanningDocumentService()
        self.llm_service = llm_service or PlanningLLMExtractionService()
        self.settings = settings or PlanningAnalysisSettings.from_env()
        self.graph = self._build()

    def invoke(
        self,
        uploads: list[UploadedDocument],
        request_id: str = "untracked",
        started_at: float | None = None,
        deadline_monotonic: float | None = None,
        max_analysis_inputs: int | None = None,
    ) -> dict[str, Any]:
        resolved_started_at = started_at if started_at is not None else perf_counter()
        resolved_deadline = (
            deadline_monotonic
            if deadline_monotonic is not None
            else (
                resolved_started_at
                + self.settings.planning_analysis_timeout_seconds
            )
        )
        return self.graph.invoke({
            "uploads": uploads,
            "request_id": request_id,
            "started_at": resolved_started_at,
            "deadline_monotonic": resolved_deadline,
            "max_analysis_inputs": (
                max_analysis_inputs
                if max_analysis_inputs is not None
                else self.settings.planning_max_analysis_chunks
            ),
        })["result"]

    def _build(self):
        workflow = StateGraph(PlanningDocumentState)
        workflow.add_node("parse_documents", self._parse_documents)
        workflow.add_node("split_documents", self._split_documents)
        workflow.add_node("select_analysis_inputs", self._select_analysis_inputs)
        workflow.add_node("extract_with_llm", self._extract_with_llm)
        workflow.add_node("consolidate_results", self._consolidate_results)
        workflow.add_node("build_response", self._build_response)
        workflow.add_edge(START, "parse_documents")
        workflow.add_edge("parse_documents", "split_documents")
        workflow.add_edge("split_documents", "select_analysis_inputs")
        workflow.add_edge("select_analysis_inputs", "extract_with_llm")
        workflow.add_edge("extract_with_llm", "consolidate_results")
        workflow.add_edge("consolidate_results", "build_response")
        workflow.add_edge("build_response", END)
        return workflow.compile()

    def _parse_documents(self, state: PlanningDocumentState) -> dict[str, Any]:
        return {"documents": self.document_service.parse_documents(state["uploads"])}

    def _split_documents(self, state: PlanningDocumentState) -> dict[str, Any]:
        chunks = self.document_service.build_chunks(state["documents"])
        return {
            "chunks": chunks,
            "vision_documents": [
                document for document in state["documents"]
                if document.processing_mode == "PDF_VISION"
            ],
            "fallback_extractions": [self.document_service.fallback_extract(chunk) for chunk in chunks],
        }

    def _select_analysis_inputs(
        self,
        state: PlanningDocumentState,
    ) -> dict[str, Any]:
        selection = select_analysis_inputs(
            chunks=state["chunks"],
            vision_documents=state["vision_documents"],
            document_names=[
                document.file_name for document in state["documents"]
            ],
            max_analysis_chunks=state["max_analysis_inputs"],
        )
        selected_inputs = [
            self._selected_input_metadata(
                candidate,
                state["chunks"],
                state["vision_documents"],
            )
            for candidate in selection.candidates
        ]
        self._audit({
            "event": "planning_analysis_inputs_selected",
            "request_id": state["request_id"],
            "file_count": len(state["uploads"]),
            "total_chunks": len(state["chunks"]),
            "vision_document_count": len(state["vision_documents"]),
            "selected_count": selection.count,
            "selected_inputs": selected_inputs,
        })
        return {
            "selected_chunk_indices": list(selection.chunk_indices),
            "selected_vision_document_indices": list(
                selection.vision_document_indices
            ),
            "selected_chunks": [
                state["chunks"][index] for index in selection.chunk_indices
            ],
            "selected_vision_documents": [
                state["vision_documents"][index]
                for index in selection.vision_document_indices
            ],
            "selected_fallback_extractions": [
                state["fallback_extractions"][index]
                for index in selection.chunk_indices
            ],
            "selected_inputs": selected_inputs,
        }

    def _extract_with_llm(self, state: PlanningDocumentState) -> dict[str, Any]:
        if perf_counter() >= state["deadline_monotonic"]:
            text_partials = state["selected_fallback_extractions"]
            vision_partials: list[dict[str, Any]] = []
            status = "FALLBACK"
            call_count = 0
            timed_out = True
            provider_fallback_used = True
        elif callable(
            getattr(type(self.llm_service), "extract_with_metrics", None)
        ):
            outcome = self.llm_service.extract_with_metrics(
                chunks=state["selected_chunks"],
                vision_documents=state["selected_vision_documents"],
                fallback_extractions=state["selected_fallback_extractions"],
                request_id=state["request_id"],
                settings=self.settings,
                deadline_monotonic=state["deadline_monotonic"],
            )
            if not isinstance(outcome, PlanningLLMExtractionOutcome):
                raise TypeError("extract_with_metrics returned an invalid outcome")
            text_partials = outcome.text_partials
            vision_partials = outcome.vision_partials
            status = outcome.status
            call_count = outcome.call_count
            timed_out = outcome.timed_out
            provider_fallback_used = outcome.fallback_used
        else:
            partials, status = self.llm_service.extract(
                chunks=state["selected_chunks"],
                vision_documents=state["selected_vision_documents"],
                fallback_extractions=state["selected_fallback_extractions"],
                request_id=state["request_id"],
            )
            selected_text_count = len(state["selected_chunks"])
            text_partials = partials[:selected_text_count]
            vision_partials = partials[selected_text_count:]
            call_count = (
                len(state["selected_chunks"])
                + len(state["selected_vision_documents"])
            )
            timed_out = False
            provider_fallback_used = status != "SUCCEEDED"

        merged_text_partials = list(state["fallback_extractions"])
        for position, chunk_index in enumerate(
            state["selected_chunk_indices"]
        ):
            if position < len(text_partials):
                merged_text_partials[chunk_index] = text_partials[position]

        fallback_used = (
            provider_fallback_used
            or len(state["chunks"]) > len(state["selected_chunk_indices"])
        )
        if fallback_used:
            status = "FALLBACK"
        return {
            "partial_extractions": [
                *merged_text_partials,
                *vision_partials,
            ],
            "llm_status": status,
            "llm_call_count": call_count,
            "timed_out": timed_out,
            "fallback_used": fallback_used,
        }

    def _consolidate_results(self, state: PlanningDocumentState) -> dict[str, Any]:
        return {"consolidated": self.document_service.consolidate(state["partial_extractions"])}

    def _build_response(self, state: PlanningDocumentState) -> dict[str, Any]:
        self._audit({
            "event": "planning_analysis_completed",
            "request_id": state["request_id"],
            "file_count": len(state["uploads"]),
            "total_chunks": len(state["chunks"]),
            "selected_count": len(state["selected_inputs"]),
            "selected_inputs": state["selected_inputs"],
            "elapsed_ms": round((perf_counter() - state["started_at"]) * 1000),
            "timed_out": state["timed_out"],
            "fallback_used": state["fallback_used"],
            "llm_call_count": state["llm_call_count"],
        })
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

    def _selected_input_metadata(
        self,
        candidate: AnalysisCandidate,
        chunks: list[dict[str, Any]],
        vision_documents: list[Any],
    ) -> dict[str, Any]:
        if candidate.kind == "TEXT":
            chunk = chunks[candidate.payload_index]
            return {
                "document_id": chunk.get("document_id"),
                "page_number": chunk.get("page_number"),
                "chunk_id": chunk.get("chunk_id"),
                "chunk_index": chunk.get("chunk_index"),
                "processing_mode": candidate.kind,
            }

        document = vision_documents[candidate.payload_index]
        return {
            "document_id": getattr(document, "document_id", None),
            "page_number": None,
            "chunk_id": None,
            "chunk_index": candidate.chunk_index,
            "processing_mode": candidate.kind,
        }

    def _audit(self, payload: dict[str, Any]) -> None:
        logger.info(
            "planning_analysis_audit %s",
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
