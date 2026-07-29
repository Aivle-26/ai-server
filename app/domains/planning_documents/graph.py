from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .document_parser import PlanningDocumentService, UploadedDocument
from .llm_service import PlanningLLMExtractionService


class PlanningDocumentState(TypedDict, total=False):
    request_id: str
    uploads: list[UploadedDocument]
    documents: list[Any]
    chunks: list[dict[str, Any]]
    vision_documents: list[Any]
    fallback_extractions: list[dict[str, Any]]
    partial_extractions: list[dict[str, Any]]
    llm_status: str
    consolidated: dict[str, Any]
    result: dict[str, Any]


class PlanningDocumentGraph:
    def __init__(
        self,
        document_service: PlanningDocumentService | None = None,
        llm_service: PlanningLLMExtractionService | None = None,
    ) -> None:
        self.document_service = document_service or PlanningDocumentService()
        self.llm_service = llm_service or PlanningLLMExtractionService()
        self.graph = self._build()

    def invoke(
        self,
        uploads: list[UploadedDocument],
        request_id: str = "untracked",
    ) -> dict[str, Any]:
        return self.graph.invoke({
            "uploads": uploads,
            "request_id": request_id,
        })["result"]

    def _build(self):
        workflow = StateGraph(PlanningDocumentState)
        workflow.add_node("parse_documents", self._parse_documents)
        workflow.add_node("split_documents", self._split_documents)
        workflow.add_node("extract_with_llm", self._extract_with_llm)
        workflow.add_node("consolidate_results", self._consolidate_results)
        workflow.add_node("build_response", self._build_response)
        workflow.add_edge(START, "parse_documents")
        workflow.add_edge("parse_documents", "split_documents")
        workflow.add_edge("split_documents", "extract_with_llm")
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

    def _extract_with_llm(self, state: PlanningDocumentState) -> dict[str, Any]:
        partials, status = self.llm_service.extract(
            chunks=state["chunks"],
            vision_documents=state["vision_documents"],
            fallback_extractions=state["fallback_extractions"],
            request_id=state["request_id"],
        )
        return {"partial_extractions": partials, "llm_status": status}

    def _consolidate_results(self, state: PlanningDocumentState) -> dict[str, Any]:
        return {"consolidated": self.document_service.consolidate(state["partial_extractions"])}

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
