import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_documents.schemas import (
    PlanningDocumentExtractionResponse,
)
from tests.e2e_stub.app import app
from tests.e2e_stub.fixtures import STUB_MARKER


class PlanningDocumentE2EStubTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_extract_preserves_file_names_and_returns_three_requirements(self):
        response = self.client.post(
            "/api/v1/planning/documents/extract",
            files=[
                ("files", ("E2E-source.txt", b"source", "text/plain")),
                ("files", ("proposal.txt", b"proposal", "text/plain")),
            ],
        )

        self.assertEqual(response.status_code, 200)
        parsed = PlanningDocumentExtractionResponse.model_validate(
            response.json()
        )
        self.assertEqual(
            [document.file_name for document in parsed.documents],
            ["E2E-source.txt", "proposal.txt"],
        )
        self.assertEqual(len(parsed.requirement_candidates), 3)
        self.assertTrue(
            all(
                STUB_MARKER in requirement.function_name
                for requirement in parsed.requirement_candidates
            )
        )
        self.assertEqual(
            {requirement.source_document for requirement in parsed.requirement_candidates},
            {"E2E-source.txt"},
        )

    def test_missing_or_empty_multipart_is_rejected(self):
        missing = self.client.post("/api/v1/planning/documents/extract")
        empty = self.client.post(
            "/api/v1/planning/documents/extract",
            files=[("files", ("empty.txt", b"", "text/plain"))],
        )

        self.assertEqual(missing.status_code, 422)
        self.assertEqual(empty.status_code, 422)

    def test_stub_does_not_attempt_non_loopback_network_access(self):
        original_connect = socket.socket.connect

        def loopback_only(sock, address):
            host = address[0]
            if host not in {"127.0.0.1", "::1", "localhost"}:
                raise AssertionError(f"non-loopback connection attempted: {host}")
            return original_connect(sock, address)

        with patch.object(socket.socket, "connect", loopback_only):
            response = self.client.post(
                "/api/v1/planning/documents/extract",
                files=[("files", ("source.txt", b"source", "text/plain"))],
            )

        self.assertEqual(response.status_code, 200)

    def test_stub_source_does_not_import_openai(self):
        source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")

        self.assertNotIn("openai", source.lower())


if __name__ == "__main__":
    unittest.main()
