import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.domains.planning_documents.chunk_selector import select_analysis_inputs
from app.domains.planning_documents.graph import PlanningDocumentGraph
from app.domains.planning_documents.llm_service import (
    PlanningLLMExtractionOutcome,
    PlanningLLMExtractionService,
)
from app.domains.planning_documents.settings import PlanningAnalysisSettings


def _chunk(
    document_id: int,
    page_number: int,
    chunk_index: int,
    text: str,
) -> dict:
    return {
        "document_id": document_id,
        "source_document": f"document-{document_id}.txt",
        "page_number": page_number,
        "chunk_id": f"{document_id}:{page_number}:{chunk_index}",
        "chunk_index": chunk_index,
        "text": text,
        "start_offset": 10,
        "end_offset": 10 + len(text),
    }


def _fallback(chunk: dict) -> dict:
    quote = chunk["text"]
    return {
        "project_info": {},
        "requirements": [{
            "function_name": "Fallback",
            "requirement_text": f"fallback-{chunk['chunk_id']}",
            "category": "FUNCTIONAL",
            "priority": "UNSPECIFIED",
            "acceptance_criteria": None,
            "due_date": None,
            "deliverable_name": None,
            "security_condition": None,
            "source_document": chunk["source_document"],
            "source_excerpt": quote,
            "evidences": [{
                "document_id": chunk["document_id"],
                "source_document": chunk["source_document"],
                "page_number": chunk["page_number"],
                "chunk_id": chunk["chunk_id"],
                "quote_text": quote,
                "start_offset": chunk["start_offset"],
                "end_offset": chunk["end_offset"],
                "bounding_boxes": [],
            }],
        }],
    }


class FakeDocumentService:
    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks

    def parse_documents(self, uploads):
        return [
            SimpleNamespace(
                file_name=chunk["source_document"],
                file_type="TXT",
                text=chunk["text"],
                processing_mode="TEXT",
                document_id=chunk["document_id"],
            )
            for chunk in self.chunks
        ]

    def build_chunks(self, documents):
        return list(self.chunks)

    def fallback_extract(self, chunk):
        return _fallback(chunk)

    def consolidate(self, partials):
        return {
            "project_info": {},
            "requirement_candidates": [
                requirement
                for partial in partials
                for requirement in partial["requirements"]
            ],
        }


class CapturingLLM:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def extract_with_metrics(
        self,
        *,
        chunks,
        vision_documents,
        fallback_extractions,
        request_id,
        settings,
        deadline_monotonic,
    ):
        self.calls.append(list(chunks))
        return PlanningLLMExtractionOutcome(
            text_partials=[_fallback(chunk) for chunk in chunks],
            vision_partials=[],
            status="SUCCEEDED",
            call_count=len(chunks),
            timed_out=False,
            fallback_used=False,
        )


class EvidencePerformanceIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chunks = [
            _chunk(101, 1, 0, "requirement requirement must provide login"),
            _chunk(102, 2, 0, "security requirement must protect data"),
            _chunk(103, 3, 0, "delivery requirement must include report"),
            _chunk(104, 4, 0, "acceptance requirement must be verified"),
            _chunk(105, 5, 0, "operation requirement must be monitored"),
        ]
        self.settings = PlanningAnalysisSettings(
            planning_analysis_timeout_seconds=50,
            planning_max_analysis_chunks=2,
            planning_readjust_max_analysis_chunks=4,
            planning_analysis_retry_count=0,
        )

    def test_settings_keep_environment_overrides_and_retry_zero(self):
        with patch.dict(
            os.environ,
            {
                "PLANNING_ANALYSIS_TIMEOUT_SECONDS": "45",
                "PLANNING_MAX_ANALYSIS_CHUNKS": "3",
                "PLANNING_READJUST_MAX_ANALYSIS_CHUNKS": "5",
                "PLANNING_ANALYSIS_RETRY_COUNT": "0",
            },
            clear=True,
        ):
            settings = PlanningAnalysisSettings.from_env()

        self.assertEqual(settings.planning_analysis_timeout_seconds, 45)
        self.assertEqual(settings.planning_max_analysis_chunks, 3)
        self.assertEqual(settings.planning_readjust_max_analysis_chunks, 5)
        self.assertEqual(settings.planning_analysis_retry_count, 0)
        with self.assertRaises(ValueError):
            PlanningAnalysisSettings(planning_analysis_retry_count=1)

    def test_default_analysis_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = PlanningAnalysisSettings.from_env()

        self.assertEqual(settings.planning_analysis_timeout_seconds, 300)
        self.assertEqual(settings.planning_max_analysis_chunks, 10)

    def test_selector_shares_the_budget_and_prioritizes_documents(self):
        selection = select_analysis_inputs(
            chunks=self.chunks,
            vision_documents=[],
            document_names=[chunk["source_document"] for chunk in self.chunks],
            max_analysis_chunks=2,
        )

        self.assertEqual(selection.count, 2)
        self.assertEqual(len(selection.chunk_indices), 2)
        self.assertEqual(selection.vision_document_indices, ())

    def test_extract_keeps_unselected_fallback_evidence_and_marks_fallback(self):
        llm = CapturingLLM()
        graph = PlanningDocumentGraph(
            document_service=FakeDocumentService(self.chunks),
            llm_service=llm,
            settings=self.settings,
        )

        result = graph.invoke([SimpleNamespace()], request_id="extract-test")

        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(len(llm.calls[0]), 2)
        self.assertEqual(result["llm_status"], "FALLBACK")
        fallback_requirement = result["requirement_candidates"][-1]
        evidence = fallback_requirement["evidences"][0]
        self.assertEqual(evidence["document_id"], 105)
        self.assertEqual(evidence["page_number"], 5)
        self.assertEqual(evidence["chunk_id"], "105:5:0")
        self.assertEqual(evidence["quote_text"], self.chunks[-1]["text"])
        self.assertEqual(evidence["start_offset"], 10)
        self.assertEqual(evidence["end_offset"], 10 + len(self.chunks[-1]["text"]))

    def test_readjust_limit_can_select_four_representative_inputs(self):
        llm = CapturingLLM()
        graph = PlanningDocumentGraph(
            document_service=FakeDocumentService(self.chunks),
            llm_service=llm,
            settings=self.settings,
        )

        graph.invoke(
            [SimpleNamespace()],
            request_id="readjust-test",
            max_analysis_inputs=self.settings.planning_readjust_max_analysis_chunks,
        )

        self.assertEqual(len(llm.calls[0]), 4)

    def test_timeout_stops_remaining_text_calls_without_sdk_retry(self):
        service = PlanningLLMExtractionService()
        structured = SimpleNamespace(
            invoke=lambda messages: (_ for _ in ()).throw(TimeoutError())
        )
        chat = SimpleNamespace(
            with_structured_output=lambda schema: structured
        )
        selected_chunks = self.chunks[:2]
        fallbacks = [_fallback(chunk) for chunk in selected_chunks]

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.ChatOpenAI",
                return_value=chat,
            ) as chat_factory,
        ):
            outcome = service.extract_with_metrics(
                chunks=selected_chunks,
                vision_documents=[],
                fallback_extractions=fallbacks,
                request_id="timeout-test",
                settings=self.settings,
                deadline_monotonic=10**9,
            )

        self.assertEqual(outcome.text_partials, fallbacks)
        self.assertTrue(outcome.timed_out)
        self.assertEqual(outcome.call_count, 1)
        self.assertEqual(chat_factory.call_count, 1)
        self.assertEqual(chat_factory.call_args.kwargs["max_retries"], 0)

    def test_evidence_validation_only_accepts_selected_chunk_ids(self):
        selected = self.chunks[0]
        result = PlanningLLMExtractionService()._normalize_result(
            {
                "project_info": {},
                "requirements": [{
                    "source_document": "invented.txt",
                    "source_excerpt": None,
                    "evidences": [
                        {
                            "chunk_id": selected["chunk_id"],
                            "quote_text": selected["text"],
                        },
                        {
                            "chunk_id": self.chunks[1]["chunk_id"],
                            "quote_text": self.chunks[1]["text"],
                        },
                    ],
                }],
            },
            source_document=selected["source_document"],
            source_text=selected["text"],
            chunk_by_id={selected["chunk_id"]: selected},
        )

        evidences = result["requirements"][0]["evidences"]
        self.assertEqual(len(evidences), 1)
        self.assertEqual(evidences[0]["chunk_id"], selected["chunk_id"])


if __name__ == "__main__":
    unittest.main()
