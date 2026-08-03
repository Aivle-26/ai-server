import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_documents.document_parser import (
    DocumentExtractionError,
)
from app.main import app


class FailingGraph:
    def invoke(self, uploads, request_id="untracked"):
        raise DocumentExtractionError("invalid document")


class CapturingGraph:
    def __init__(self):
        self.request_id = None

    def invoke(self, uploads, request_id="untracked"):
        self.request_id = request_id
        return {
            "project_info": {},
            "requirement_candidates": [],
            "documents": [{
                "file_name": uploads[0].file_name,
                "file_type": "TXT",
                "character_count": len(uploads[0].content),
                "processing_mode": "TEXT",
            }],
            "llm_status": "SUCCEEDED",
        }


class PlanningDocumentRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_text_upload_returns_json_contract_without_network(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post(
                "/api/v1/planning/documents/extract",
                files={
                    "files": (
                        "rfp.txt",
                        b"Project name: AIPM\nREQ-001 must support login.",
                        "text/plain",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("application/json")
        )
        self.assertEqual(response.json()["llm_status"], "FALLBACK")
        self.assertEqual(response.json()["documents"][0]["file_name"], "rfp.txt")

    def test_file_count_limit_returns_422_before_graph(self):
        files = [
            ("files", ("one.txt", b"one", "text/plain")),
            ("files", ("two.txt", b"two", "text/plain")),
        ]
        with patch(
            "app.domains.planning_documents.router.MAX_FILE_COUNT", 1
        ):
            response = self.client.post(
                "/api/v1/planning/documents/extract", files=files
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("최대 1개", response.json()["message"])

    def test_file_size_limit_returns_413(self):
        with patch(
            "app.domains.planning_documents.router.MAX_FILE_SIZE", 3
        ):
            response = self.client.post(
                "/api/v1/planning/documents/extract",
                files={"files": ("large.txt", b"1234", "text/plain")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("20MB", response.json()["message"])

    def test_document_error_maps_to_422(self):
        with patch(
            "app.domains.planning_documents.router.planning_document_graph",
            FailingGraph(),
        ):
            response = self.client.post(
                "/api/v1/planning/documents/extract",
                files={"files": ("bad.txt", b"content", "text/plain")},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["message"], "invalid document")

    def test_request_id_is_generated_and_logged_with_completion_status(self):
        graph = CapturingGraph()
        with (
            patch(
                "app.domains.planning_documents.router.planning_document_graph",
                graph,
            ),
            self.assertLogs("uvicorn.error", level="INFO") as captured,
        ):
            response = self.client.post(
                "/api/v1/planning/documents/extract",
                files={"files": ("ok.txt", b"content", "text/plain")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(graph.request_id or "", r"^[0-9a-f]{32}$")
        logs = "\n".join(captured.output)
        self.assertIn('"event":"planning_extract_completed"', logs)
        self.assertIn(f'"request_id":"{graph.request_id}"', logs)
        self.assertIn('"llm_status":"SUCCEEDED"', logs)


if __name__ == "__main__":
    unittest.main()
