import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_documents.document_parser import (
    DocumentExtractionError,
)
from app.main import app


class FailingGraph:
    def invoke(self, uploads):
        raise DocumentExtractionError("invalid document")


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
        self.assertEqual(response.json()["llm_status"], "SKIPPED_NO_API_KEY")
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
        self.assertIn("최대 1개", response.json()["detail"])

    def test_file_size_limit_returns_413(self):
        with patch(
            "app.domains.planning_documents.router.MAX_FILE_SIZE", 3
        ):
            response = self.client.post(
                "/api/v1/planning/documents/extract",
                files={"files": ("large.txt", b"1234", "text/plain")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertIn("20MB", response.json()["detail"])

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
        self.assertEqual(response.json()["detail"], "invalid document")


if __name__ == "__main__":
    unittest.main()
