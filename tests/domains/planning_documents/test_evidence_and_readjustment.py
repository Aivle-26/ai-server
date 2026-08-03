import io
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from app.domains.planning_documents.document_parser import (
    ParsedDocument,
    ParsedPage,
    PlanningDocumentService,
    UploadedDocument,
)
from app.domains.planning_documents.llm_service import (
    PlanningLLMExtractionService,
)
from app.domains.planning_documents.readjustment import (
    RequirementReadjustmentService,
)
from app.domains.planning_documents.schemas import ExistingRequirement
from app.main import app


class ManifestCapturingGraph:
    def __init__(self):
        self.uploads = []

    def invoke(self, uploads, request_id="untracked"):
        self.uploads = uploads
        return {
            "project_info": {},
            "requirement_candidates": [],
            "documents": [
                {
                    "file_name": upload.file_name,
                    "file_type": "TXT",
                    "character_count": len(upload.content),
                    "processing_mode": "TEXT",
                }
                for upload in uploads
            ],
            "llm_status": "SUCCEEDED",
        }


class PlanningEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.document_service = PlanningDocumentService()
        self.llm_service = PlanningLLMExtractionService()

    def test_extract_accepts_optional_manifest_and_preserves_document_id(self):
        graph = ManifestCapturingGraph()
        client = TestClient(app)
        with patch(
            "app.domains.planning_documents.router.planning_document_graph",
            graph,
        ):
            response = client.post(
                "/api/v1/planning/documents/extract",
                files={"files": ("rfp.txt", b"requirement", "text/plain")},
                data={
                    "document_manifest": json.dumps([
                        {"document_id": 12, "file_name": "rfp.txt"}
                    ])
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(graph.uploads[0].document_id, 12)

    def test_manifest_rejects_count_mismatch_and_duplicate_ids(self):
        client = TestClient(app)
        files = [
            ("files", ("one.txt", b"one", "text/plain")),
            ("files", ("two.txt", b"two", "text/plain")),
        ]
        for manifest in (
            [{"document_id": 1, "file_name": "one.txt"}],
            [
                {"document_id": 1, "file_name": "one.txt"},
                {"document_id": 1, "file_name": "two.txt"},
            ],
        ):
            with self.subTest(manifest=manifest):
                response = client.post(
                    "/api/v1/planning/documents/extract",
                    files=files,
                    data={"document_manifest": json.dumps(manifest)},
                )
                self.assertEqual(response.status_code, 422)

    def test_readjust_endpoint_keeps_unmentioned_requirement_pending(self):
        graph = ManifestCapturingGraph()
        client = TestClient(app)
        with patch(
            "app.domains.planning_documents.router.planning_document_graph",
            graph,
        ):
            response = client.post(
                "/api/v1/planning/documents/readjust",
                files={"files": ("change.txt", b"new context", "text/plain")},
                data={
                    "document_manifest": json.dumps([
                        {"document_id": 22, "file_name": "change.txt"}
                    ]),
                    "existing_requirements": json.dumps([{
                        "requirement_id": 10,
                        "function_name": "Login",
                        "requirement_text": "Users must log in.",
                        "source_document": "base.pdf",
                    }]),
                },
            )

        self.assertEqual(response.status_code, 200)
        candidate = response.json()["change_candidates"][0]
        self.assertEqual(candidate["change_type"], "UNCHANGED")
        self.assertEqual(candidate["review_status"], "PENDING_REVIEW")
        self.assertEqual(candidate["evidences"], [])

    def test_pdf_pages_are_one_based_and_chunks_never_cross_pages(self):
        pdf = self._two_page_pdf()
        document = self.document_service.parse_documents([
            UploadedDocument(
                "fixture.pdf",
                "application/pdf",
                pdf,
                document_id=91,
            )
        ])[0]

        self.assertEqual(
            [page.page_number for page in document.pages],
            [1, 2],
        )
        chunks = self.document_service.build_chunks([document])
        self.assertEqual(
            {chunk["page_number"] for chunk in chunks},
            {1, 2},
        )
        self.assertEqual(chunks[0]["chunk_id"], "91:1:1")
        self.assertEqual(chunks[-1]["chunk_id"], "91:2:1")

    def test_non_pdf_document_has_no_invented_page_number(self):
        document = self.document_service.parse_documents([
            UploadedDocument("notes.txt", "text/plain", b"plain requirement")
        ])[0]
        chunk = self.document_service.build_chunks([document])[0]

        self.assertIsNone(document.pages[0].page_number)
        self.assertIsNone(chunk["page_number"])

    def test_legacy_uploads_with_duplicate_names_get_distinct_chunk_ids(self):
        documents = self.document_service.parse_documents([
            UploadedDocument("notes.txt", "text/plain", b"first requirement"),
            UploadedDocument("notes.txt", "text/plain", b"second requirement"),
        ])
        chunks = self.document_service.build_chunks(documents)

        self.assertEqual(len(chunks), 2)
        self.assertNotEqual(chunks[0]["chunk_id"], chunks[1]["chunk_id"])

    def test_evidence_reference_requires_real_chunk_and_quote(self):
        chunk = {
            "chunk_id": "7:3:1",
            "document_id": 7,
            "source_document": "rfp.pdf",
            "page_number": 3,
            "text": "Login must support\nmulti factor authentication.",
            "start_offset": 20,
        }
        valid = self.llm_service._resolve_evidence(
            {
                "chunk_id": "7:3:1",
                "quote_text": "Login must support multi factor authentication.",
            },
            {"7:3:1": chunk},
        )

        self.assertIsNotNone(valid)
        self.assertEqual(valid["page_number"], 3)
        self.assertEqual(valid["start_offset"], 20)
        self.assertEqual(valid["bounding_boxes"], [])
        self.assertIsNone(self.llm_service._resolve_evidence(
            {"chunk_id": "missing", "quote_text": "Login"},
            {"7:3:1": chunk},
        ))
        self.assertIsNone(self.llm_service._resolve_evidence(
            {"chunk_id": "7:3:1", "quote_text": "invented quote"},
            {"7:3:1": chunk},
        ))

    def test_duplicate_requirements_merge_multi_document_evidence(self):
        evidence_one = self._evidence(1, 1, "1:1:1", "Login required")
        evidence_two = self._evidence(2, 4, "2:4:1", "Login required")
        result = self.document_service.consolidate([
            {
                "project_info": {},
                "requirements": [{
                    "function_name": "Login",
                    "requirement_text": "Users can log in.",
                    "source_document": "one.pdf",
                    "evidences": [evidence_one],
                }],
            },
            {
                "project_info": {},
                "requirements": [{
                    "function_name": "Login",
                    "requirement_text": "Users can log in!",
                    "source_document": "two.pdf",
                    "evidences": [evidence_two],
                }],
            },
        ])

        requirement = result["requirement_candidates"][0]
        self.assertEqual(len(requirement["evidences"]), 2)
        self.assertEqual(requirement["source_document"], "one.pdf")
        self.assertEqual(requirement["source_excerpt"], "Login required")

    def test_vision_normalization_does_not_invent_page_or_box(self):
        extracted = {
            "project_info": {},
            "requirements": [{
                "function_name": "Login",
                "requirement_text": "Users can log in.",
                "source_document": "scan.pdf",
                "source_excerpt": "Users can log in.",
                "evidences": [{
                    "chunk_id": "invented:2:1",
                    "quote_text": "Users can log in.",
                }],
            }],
        }
        normalized = self.llm_service._normalize_result(
            extracted,
            source_document="scan.pdf",
            source_text=None,
            chunk_by_id={},
        )

        self.assertEqual(normalized["requirements"][0]["evidences"], [])

    def _two_page_pdf(self) -> bytes:
        writer = PdfWriter()
        for text in (
            "Page one requirement " * 6,
            "Page two requirement " * 6,
        ):
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            resources = DictionaryObject({
                NameObject("/Font"): DictionaryObject({
                    NameObject("/F1"): writer._add_object(font),
                }),
            })
            page[NameObject("/Resources")] = resources
            stream = DecodedStreamObject()
            stream.set_data(
                f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    def _evidence(
        self,
        document_id: int,
        page_number: int,
        chunk_id: str,
        quote_text: str,
    ) -> dict:
        return {
            "document_id": document_id,
            "source_document": "one.pdf" if document_id == 1 else "two.pdf",
            "page_number": page_number,
            "chunk_id": chunk_id,
            "quote_text": quote_text,
            "start_offset": 0,
            "end_offset": len(quote_text),
            "bounding_boxes": [],
        }


class RequirementReadjustmentTest(unittest.TestCase):
    def setUp(self):
        self.service = RequirementReadjustmentService()
        self.existing = ExistingRequirement(
            requirement_id=10,
            function_name="Login",
            requirement_text="Users must log in.",
            source_document="base.pdf",
        )

    def test_unmentioned_requirement_is_unchanged_not_removed(self):
        changes = self.service.build_changes([self.existing], [])

        self.assertEqual(changes[0]["change_type"], "UNCHANGED")
        self.assertEqual(changes[0]["evidences"], [])

    def test_same_text_with_explicit_priority_change_is_modified(self):
        changed = self._candidate(
            1,
            "Login",
            "Users must log in.",
        )
        changed["priority"] = "HIGH"

        changes = self.service.build_changes([self.existing], [changed])

        self.assertEqual(changes[0]["change_type"], "MODIFIED")

    def test_explicit_removal_is_removed_and_new_requirement_is_added(self):
        extracted = [
            self._candidate(
                1,
                "Login cancellation",
                "Login requirement is removed.",
            ),
            self._candidate(
                2,
                "Audit",
                "The system must retain audit logs.",
            ),
        ]
        changes = self.service.build_changes([self.existing], extracted)

        self.assertEqual(
            [change["change_type"] for change in changes],
            ["REMOVED", "ADDED"],
        )
        self.assertTrue(all(
            change["review_status"] == "PENDING_REVIEW"
            for change in changes
        ))

    def test_generic_token_does_not_remove_unrelated_requirement(self):
        extracted = [
            self._candidate(
                1,
                "Audit logging",
                "Users are notified when audit logging is removed.",
            )
        ]

        changes = self.service.build_changes([self.existing], extracted)

        self.assertEqual(changes[0]["change_type"], "UNCHANGED")

    def _candidate(
        self,
        requirement_id: int,
        function_name: str,
        requirement_text: str,
    ) -> dict:
        return {
            "requirement_id": requirement_id,
            "function_name": function_name,
            "requirement_text": requirement_text,
            "source_document": "change.txt",
            "evidences": [],
        }


if __name__ == "__main__":
    unittest.main()
