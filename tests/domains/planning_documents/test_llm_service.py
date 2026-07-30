import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.domains.planning_documents.document_parser import ParsedDocument
from app.domains.planning_documents.llm_service import (
    DocumentChunkExtraction,
    ExtractedProjectInfo,
    ExtractedRequirement,
    PlanningLLMExtractionService,
)


FALLBACK = {
    "project_info": {"project_name": "Fallback"},
    "requirements": [],
}
CHUNK = {
    "source_document": "rfp.txt",
    "chunk_index": 1,
    "text": "Users can log in.",
}
SECOND_CHUNK = {
    "source_document": "rfp.txt",
    "chunk_index": 2,
    "text": "The system must protect user data.",
}
SECOND_FALLBACK = {
    "project_info": {"project_name": "Second fallback"},
    "requirements": [],
}


class PlanningDocumentLlmServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningLLMExtractionService()

    def test_missing_key_returns_exact_fallback_without_clients(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.ChatOpenAI"
            ) as chat,
            patch(
                "app.domains.planning_documents.llm_service.OpenAI"
            ) as openai,
        ):
            results, status = self.service.extract(
                [CHUNK], [], [FALLBACK]
            )

        self.assertEqual(results, [FALLBACK])
        self.assertEqual(status, "SKIPPED_NO_API_KEY")
        chat.assert_not_called()
        openai.assert_not_called()

    def test_text_structured_result_is_normalized_to_real_source(self):
        structured = MagicMock()
        structured.invoke.return_value = DocumentChunkExtraction(
            project_info=ExtractedProjectInfo(project_name="AIPM"),
            requirements=[
                ExtractedRequirement(
                    function_name="Login",
                    requirement_text="Users can log in.",
                    source_document="invented.txt",
                    source_excerpt="not in source",
                )
            ],
        )
        chat = MagicMock()
        chat.with_structured_output.return_value = structured

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.ChatOpenAI",
                return_value=chat,
            ),
        ):
            results, status = self.service.extract(
                [CHUNK], [], [FALLBACK]
            )

        requirement = results[0]["requirements"][0]
        self.assertEqual(status, "SUCCEEDED")
        self.assertEqual(requirement["source_document"], "rfp.txt")
        self.assertIsNone(requirement["source_excerpt"])

    def test_success_logs_one_provider_pair_without_fallback(self):
        structured = MagicMock()
        structured.invoke.return_value = DocumentChunkExtraction(
            project_info=ExtractedProjectInfo(project_name="AIPM"),
            requirements=[],
        )
        chat = MagicMock()
        chat.with_structured_output.return_value = structured

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.ChatOpenAI",
                return_value=chat,
            ),
            self.assertLogs("uvicorn.error", level="INFO") as captured,
        ):
            _, status = self.service.extract(
                [CHUNK],
                [],
                [FALLBACK],
                request_id="request-123",
            )

        logs = "\n".join(captured.output)
        self.assertEqual(status, "SUCCEEDED")
        self.assertEqual(logs.count('"event":"provider_call_started"'), 1)
        self.assertEqual(logs.count('"event":"provider_call_succeeded"'), 1)
        self.assertNotIn('"event":"fallback_used"', logs)
        self.assertIn('"request_id":"request-123"', logs)
        self.assertNotIn("test-key", logs)

    def test_text_timeout_uses_matching_fallback(self):
        structured = MagicMock()
        structured.invoke.side_effect = TimeoutError("timeout")
        chat = MagicMock()
        chat.with_structured_output.return_value = structured

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.ChatOpenAI",
                return_value=chat,
            ) as chat_factory,
        ):
            results, status = self.service.extract(
                [CHUNK, SECOND_CHUNK],
                [],
                [FALLBACK, SECOND_FALLBACK],
            )

        self.assertEqual(results, [FALLBACK, SECOND_FALLBACK])
        self.assertEqual(status, "FALLBACK")
        self.assertEqual(structured.invoke.call_count, 1)
        self.assertEqual(chat_factory.call_count, 1)
        self.assertEqual(
            chat_factory.call_args.kwargs["max_retries"],
            0,
        )
        self.assertLessEqual(
            chat_factory.call_args.kwargs["timeout"],
            180,
        )

    def test_failure_audit_omits_exception_message_and_input_content(self):
        structured = MagicMock()
        structured.invoke.side_effect = TimeoutError(
            "secret-prompt-content"
        )
        chat = MagicMock()
        chat.with_structured_output.return_value = structured

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.ChatOpenAI",
                return_value=chat,
            ),
            self.assertLogs("uvicorn.error", level="INFO") as captured,
        ):
            _, status = self.service.extract(
                [CHUNK],
                [],
                [FALLBACK],
                request_id="request-failed",
            )

        logs = "\n".join(captured.output)
        self.assertEqual(status, "FALLBACK")
        self.assertIn('"event":"provider_call_failed"', logs)
        self.assertIn('"exception_type":"TimeoutError"', logs)
        self.assertIn('"event":"fallback_used"', logs)
        self.assertNotIn("secret-prompt-content", logs)
        self.assertNotIn(CHUNK["text"], logs)
        self.assertNotIn("test-key", logs)

    def test_vision_client_creation_failure_is_contained(self):
        document = ParsedDocument(
            "scan.pdf", "PDF", "", b"%PDF", "PDF_VISION"
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_documents.llm_service.OpenAI",
                side_effect=RuntimeError("bad client"),
            ),
        ):
            results, status = self.service.extract([], [document], [])

        self.assertEqual(results, [])
        self.assertEqual(status, "FALLBACK")

    def test_vision_client_disables_sdk_retries(self):
        document = ParsedDocument(
            "scan.pdf", "PDF", "", b"%PDF", "PDF_VISION"
        )
        service = PlanningLLMExtractionService()
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "test-key"},
                clear=True,
            ),
            patch(
                "app.domains.planning_documents.llm_service.OpenAI"
            ) as openai,
            patch.object(
                service,
                "_extract_pdf_with_vision",
                return_value=FALLBACK,
            ),
        ):
            results, status = service.extract([], [document], [])

        self.assertEqual(results, [FALLBACK])
        self.assertEqual(status, "SUCCEEDED")
        self.assertEqual(openai.call_count, 1)
        self.assertEqual(openai.call_args.kwargs["max_retries"], 0)

    def test_vision_none_output_is_rejected_and_store_is_disabled(self):
        responses = MagicMock()
        responses.parse.return_value = SimpleNamespace(output_parsed=None)
        client = SimpleNamespace(responses=responses)
        document = ParsedDocument(
            "scan.pdf", "PDF", "", b"%PDF-data", "PDF_VISION"
        )

        with self.assertRaisesRegex(ValueError, "구조화된 PDF"):
            self.service._extract_pdf_with_vision(client, document)

        request = responses.parse.call_args.kwargs
        self.assertFalse(request["store"])
        self.assertIs(request["text_format"], DocumentChunkExtraction)
        content = request["input"][0]["content"]
        self.assertEqual(content[0]["type"], "input_file")
        self.assertTrue(
            content[0]["file_data"].startswith(
                "data:application/pdf;base64,"
            )
        )


if __name__ == "__main__":
    unittest.main()
