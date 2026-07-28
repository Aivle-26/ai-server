from datetime import date
from pathlib import Path
import tempfile
import unittest

import fitz

from app.domains.project_risk.services.artifact_management_service import (
    ArtifactManagementService,
)
from app.domains.project_risk.services.artifact_security_service import (
    ArtifactSecurityService,
)
from app.domains.project_risk.services.document_service import DocumentService
from app.domains.project_risk.services.progress_delay_service import (
    ProgressDelayService,
)
from app.domains.project_risk.services.schedule_risk_service import (
    analyze_schedule_task,
    calculate_expected_progress,
)


class ArtifactManagementServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = ArtifactManagementService()

    def test_register_uses_semantic_latest_version_and_latest_approval(self):
        result = self.service.build_register(
            project_id=7,
            required_artifacts=[
                {
                    "artifact_code": "REQ",
                    "artifact_name": "Requirements",
                    "artifact_type": "DOCUMENT",
                    "due_date": "2026-07-30",
                }
            ],
            stored_documents=[
                {
                    "artifact_code": "REQ",
                    "document_id": 10,
                    "storage_path": "documents/req",
                }
            ],
            version_histories=[
                {
                    "artifact_code": "REQ",
                    "version": "1.2",
                    "created_at": "2026-07-20T10:00:00",
                },
                {
                    "artifact_code": "REQ",
                    "version": "1.10",
                    "created_at": "2026-07-19T10:00:00",
                },
            ],
            approval_histories=[
                {
                    "artifact_code": "REQ",
                    "approval_status": "REJECTED",
                    "reviewed_at": "2026-07-20T10:00:00",
                },
                {
                    "artifact_code": "REQ",
                    "approval_status": "APPROVED",
                    "approved_by": "PM-1",
                    "reviewed_at": "2026-07-21T10:00:00",
                },
            ],
            reference_date="2026-07-28",
        )

        item = result["artifact_register"][0]
        self.assertEqual(item["latest_version"], "1.10")
        self.assertEqual(item["status"], "APPROVED")
        self.assertEqual(item["approved_by"], "PM-1")
        self.assertFalse(item["requires_action"])
        self.assertEqual(
            result["artifact_summary"]["completion_rate"], 100.0
        )

    def test_register_classifies_missing_pending_rejected_and_overdue(self):
        result = self.service.build_register(
            project_id=7,
            required_artifacts=[
                {
                    "artifact_code": "MISSING",
                    "artifact_name": "Missing",
                    "due_date": "2026-07-20",
                },
                {
                    "artifact_code": "PENDING",
                    "artifact_name": "Pending",
                    "due_date": "2026-07-20",
                },
                {
                    "artifact_code": "REJECTED",
                    "artifact_name": "Rejected",
                },
            ],
            stored_documents=[
                {"artifact_code": "PENDING", "document_id": 1},
                {"artifact_code": "REJECTED", "document_id": 2},
            ],
            version_histories=[],
            approval_histories=[
                {
                    "artifact_code": "PENDING",
                    "approval_status": "PENDING",
                    "reviewed_at": "2026-07-21",
                },
                {
                    "artifact_code": "REJECTED",
                    "approval_status": "REJECTED",
                    "reviewed_at": "2026-07-21",
                },
            ],
            reference_date="2026-07-28",
        )

        statuses = {
            item["artifact_code"]: item["status"]
            for item in result["artifact_register"]
        }
        self.assertEqual(statuses["MISSING"], "OVERDUE_NOT_REGISTERED")
        self.assertEqual(statuses["PENDING"], "OVERDUE_APPROVAL")
        self.assertEqual(statuses["REJECTED"], "REJECTED")
        self.assertEqual(result["artifact_summary"]["overdue_count"], 2)
        self.assertEqual(len(result["uncompleted_artifacts"]), 3)

    def test_empty_register_and_invalid_input_contracts(self):
        result = self.service.build_register(7, [], [], [], [], "2026-07-28")
        self.assertEqual(result["artifact_summary"]["completion_rate"], 0.0)
        with self.assertRaises(ValueError):
            self.service.build_register(0, [], [], [], [])
        with self.assertRaisesRegex(ValueError, "artifact_code"):
            self.service.build_register(
                7, [{"artifact_name": "Missing code"}], [], [], []
            )


class ArtifactSecurityServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = ArtifactSecurityService()

    def test_blank_file_or_content_is_rejected(self):
        for file_name, content in (("", "text"), ("report.txt", " ")):
            with self.subTest(file_name=file_name), self.assertRaises(
                ValueError
            ):
                self.service.inspect(file_name, "REPORT", content)

    def test_sensitive_content_is_scored_masked_and_blocked(self):
        result = self.service.inspect(
            "report.txt",
            " report ",
            (
                "대외비 user@example.com 010-1234-5678 "
                "900101-1234567 password is present"
            ),
        )

        self.assertEqual(result["file"]["document_type"], "REPORT")
        self.assertEqual(result["inspection"]["risk_level"], "CRITICAL")
        self.assertFalse(result["inspection"]["registration_allowed"])
        self.assertNotIn("user@example.com", result["masked_preview"])
        self.assertNotIn("010-1234-5678", result["masked_preview"])
        self.assertTrue(result["recommended_actions"])

    def test_clean_content_is_allowed(self):
        result = self.service.inspect(
            "report.txt", "REPORT", "Project progress is on track."
        )
        self.assertEqual(result["inspection"]["risk_score"], 0)
        self.assertTrue(result["inspection"]["registration_allowed"])


class ProgressAndScheduleRiskServiceTest(unittest.TestCase):
    def test_progress_delay_handles_no_tasks_and_critical_member(self):
        result = ProgressDelayService().analyze(
            [
                {
                    "member_id": 1,
                    "member_name": "Idle",
                    "assigned_task_count": 0,
                    "completed_task_count": 0,
                    "overdue_task_count": 0,
                },
                {
                    "member_id": 2,
                    "member_name": "Delayed",
                    "assigned_task_count": 10,
                    "completed_task_count": 1,
                    "overdue_task_count": 5,
                },
            ]
        )

        by_name = {item["member_name"]: item for item in result["members"]}
        self.assertEqual(by_name["Idle"]["progress_rate"], 100)
        self.assertEqual(by_name["Idle"]["delay_level"], "LOW")
        self.assertEqual(by_name["Delayed"]["delay_level"], "CRITICAL")
        self.assertEqual(len(result["delay_members"]), 1)

    def test_expected_progress_date_boundaries(self):
        start = date(2026, 7, 20)
        due = date(2026, 7, 30)
        self.assertEqual(
            calculate_expected_progress(start, due, date(2026, 7, 19)), 0
        )
        self.assertEqual(
            calculate_expected_progress(start, due, date(2026, 7, 25)), 50
        )
        self.assertEqual(
            calculate_expected_progress(start, due, date(2026, 7, 30)), 100
        )
        self.assertEqual(
            calculate_expected_progress(start, start, start), 100
        )

class DocumentServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = DocumentService()

    def test_chunking_validates_sizes_and_preserves_overlap(self):
        for chunk_size, overlap in ((0, 0), (5, -1), (5, 5)):
            with self.subTest(
                chunk_size=chunk_size, overlap=overlap
            ), self.assertRaises(ValueError):
                self.service.split_text_into_chunks(
                    "abcdef", chunk_size, overlap
                )

        chunks = self.service.split_text_into_chunks(
            "abcdefghij", chunk_size=6, overlap_size=2
        )
        self.assertEqual(
            [item["chunk_text"] for item in chunks],
            ["abcdef", "efghij"],
        )
        self.assertEqual(self.service.split_text_into_chunks("   "), [])

    def test_pdf_processing_uses_local_temporary_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Project requirement")
            document.save(path)
            document.close()

            result = self.service.process_pdf(
                str(path), chunk_size=10, overlap_size=2
            )

        self.assertEqual(result["file_name"], "sample.pdf")
        self.assertEqual(result["page_count"], 1)
        self.assertIn("Project requirement", result["text_content"])
        self.assertGreater(result["chunk_count"], 1)

    def test_pdf_processing_rejects_missing_and_non_pdf_files(self):
        with self.assertRaises(FileNotFoundError):
            self.service.extract_pdf_text("missing.pdf")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text("text", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PDF"):
                self.service.extract_pdf_text(str(path))


if __name__ == "__main__":
    unittest.main()
