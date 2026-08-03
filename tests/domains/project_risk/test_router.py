from datetime import date
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.project_risk.router import get_risk_level
from app.main import app


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 7, 28)


class ProjectRiskRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_risk_level_boundaries(self):
        expected = {
            0: "LOW",
            34: "LOW",
            35: "MEDIUM",
            64: "MEDIUM",
            65: "HIGH",
            84: "HIGH",
            85: "CRITICAL",
            100: "CRITICAL",
        }
        for score, level in expected.items():
            with self.subTest(score=score):
                self.assertEqual(get_risk_level(score), level)

    def test_impact_assessment_calculates_weighted_scores(self):
        response = self.client.post(
            "/api/v1/risk/impact-assessment",
            json={
                "project_id": 7,
                "requirement_id": 10,
                "change_title": "Scope update",
                "change_description": "Add a new workflow",
                "affected_task_count": 5,
                "affected_member_count": 4,
                "remaining_days": 10,
                "additional_work_days": 20,
                "scope_changed": True,
                "database_changed": True,
                "api_changed": True,
                "ui_changed": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["schedule_impact_score"], 90)
        self.assertEqual(body["scope_impact_score"], 80)
        self.assertEqual(body["resource_impact_score"], 60)
        self.assertEqual(body["technical_impact_score"], 75)
        self.assertEqual(body["impact_score"], 79)
        self.assertEqual(body["impact_level"], "HIGH")

    def test_impact_assessment_rejects_negative_counts(self):
        response = self.client.post(
            "/api/v1/risk/impact-assessment",
            json={
                "project_id": 7,
                "change_title": "Bad",
                "change_description": "Bad count",
                "affected_task_count": -1,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_reassignment_recommends_highest_scoring_candidate(self):
        response = self.client.post(
            "/api/v1/risk/assignee-reassignment",
            json={
                "project_id": 7,
                "task_id": 3,
                "task_name": "Build API",
                "required_role": "BACKEND",
                "required_skills": ["Java", "Spring"],
                "current_assignee": {
                    "member_id": 1,
                    "member_name": "Current",
                    "skills": ["Java"],
                    "workload_rate": 95,
                    "overdue_task_count": 2,
                },
                "candidates": [
                    {
                        "member_id": 2,
                        "member_name": "Best",
                        "role": "backend",
                        "skills": ["JAVA", "SPRING"],
                        "workload_rate": 20,
                        "overdue_task_count": 0,
                    },
                    {
                        "member_id": 3,
                        "member_name": "Alternative",
                        "role": "FRONTEND",
                        "skills": ["Java"],
                        "workload_rate": 10,
                        "overdue_task_count": 0,
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["reassignment_required"])
        self.assertEqual(body["recommended_assignee"]["member_name"], "Best")
        self.assertEqual(
            body["alternative_candidates"][0]["member_name"], "Alternative"
        )

    def test_reassignment_handles_no_candidates(self):
        response = self.client.post(
            "/api/v1/risk/assignee-reassignment",
            json={
                "project_id": 7,
                "task_id": 3,
                "task_name": "Build API",
                "required_role": "BACKEND",
                "current_assignee": {
                    "member_id": 1,
                    "member_name": "Current",
                },
                "candidates": [],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["recommended_assignee"])
        self.assertFalse(response.json()["reassignment_required"])

    def test_artifact_security_masks_all_detected_values(self):
        private_key_header = "-----BEGIN " + "PRIVATE KEY-----"
        content = (
            "phone 010-1234-5678 email user@example.com "
            "resident 900101-1234567 api_key=testtoken123 "
            "host 192.168.0.10 "
            + private_key_header
        )
        response = self.client.post(
            "/api/v1/risk/artifact-security",
            json={
                "project_id": 7,
                "artifact_name": "Security report",
                "artifact_type": "REPORT",
                "text_content": content,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["security_risk_score"], 100)
        self.assertEqual(body["security_risk_level"], "CRITICAL")
        self.assertFalse(body["registration_allowed"])
        self.assertEqual(
            {item["detection_type"] for item in body["detections"]},
            {
                "PHONE_NUMBER",
                "EMAIL",
                "RESIDENT_NUMBER",
                "API_KEY",
                "PRIVATE_IP",
                "PRIVATE_KEY",
            },
        )
        for sensitive in (
            "010-1234-5678",
            "user@example.com",
            "900101-1234567",
            "testtoken123",
            "192.168.0.10",
            private_key_header,
        ):
            self.assertNotIn(sensitive, body["masked_content"])

    def test_clean_artifact_is_allowed(self):
        response = self.client.post(
            "/api/v1/risk/artifact-security",
            json={
                "project_id": 7,
                "artifact_name": "Clean report",
                "artifact_type": "REPORT",
                "text_content": "This document contains project progress only.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["registration_allowed"])
        self.assertEqual(response.json()["detections"], [])

    def test_artifact_status_reports_missing_pending_and_overdue(self):
        with patch("app.domains.project_risk.router.date", FixedDate):
            response = self.client.post(
                "/api/v1/risk/artifact-status",
                json={
                    "project_id": 7,
                    "required_artifacts": ["Requirements", "Test results"],
                    "registered_artifacts": [
                        {
                            "artifact_name": "Requirements",
                            "artifact_type": "DOCUMENT",
                            "approved": False,
                            "due_date": "2026-07-20",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["registered_count"], 1)
        self.assertEqual(body["approved_count"], 0)
        self.assertEqual(body["missing_artifacts"], ["Test results"])
        self.assertEqual(body["unapproved_artifacts"], ["Requirements"])
        self.assertEqual(body["overdue_artifacts"], ["Requirements"])

    def test_member_delay_returns_400_for_impossible_counts(self):
        response = self.client.post(
            "/api/v1/risk/member-delay",
            json={
                "project_id": 7,
                "members": [
                    {
                        "member_id": 1,
                        "member_name": "Kim",
                        "assigned_task_count": 1,
                        "completed_task_count": 2,
                        "overdue_task_count": 0,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("완료 업무 수", response.json()["message"])

    def test_member_delay_sorts_highest_risk_first(self):
        response = self.client.post(
            "/api/v1/risk/member-delay",
            json={
                "project_id": 7,
                "members": [
                    {
                        "member_id": 1,
                        "member_name": "Healthy",
                        "assigned_task_count": 0,
                        "completed_task_count": 0,
                        "overdue_task_count": 0,
                    },
                    {
                        "member_id": 2,
                        "member_name": "Delayed",
                        "assigned_task_count": 10,
                        "completed_task_count": 1,
                        "overdue_task_count": 6,
                        "average_delay_days": 5,
                        "days_since_last_update": 8,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["member_results"][0]["member_name"], "Delayed")
        self.assertEqual(body["member_results"][1]["completion_rate"], 100.0)
        self.assertEqual(body["high_risk_member_count"], 1)

    def test_schedule_risk_handles_overdue_future_and_completed_tasks(self):
        response = self.client.post(
            "/api/v1/risk/schedule-wbs-risk",
            json={
                "project_id": 7,
                "evaluation_date": "2026-07-28",
                "tasks": [
                    {
                        "task_id": 1,
                        "task_name": "Overdue",
                        "start_date": "2026-07-01",
                        "due_date": "2026-07-20",
                        "progress": 10,
                        "status": "IN_PROGRESS",
                    },
                    {
                        "task_id": 2,
                        "task_name": "Future",
                        "start_date": "2026-08-01",
                        "due_date": "2026-08-10",
                        "progress": 0,
                        "status": "TODO",
                    },
                    {
                        "task_id": 3,
                        "task_name": "Done",
                        "start_date": "2026-07-01",
                        "due_date": "2026-07-10",
                        "progress": 100,
                        "status": "DONE",
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        by_id = {item["task_id"]: item for item in body["task_results"]}
        self.assertEqual(by_id[1]["traffic_light"], "RED")
        self.assertEqual(by_id[2]["expected_progress"], 0)
        self.assertEqual(by_id[2]["traffic_light"], "GREEN")
        self.assertEqual(by_id[3]["risk_score"], 0)
        self.assertEqual(body["overall_traffic_light"], "RED")

    def test_schedule_risk_accepts_empty_task_list(self):
        response = self.client.post(
            "/api/v1/risk/schedule-wbs-risk",
            json={
                "project_id": 7,
                "evaluation_date": "2026-07-28",
                "tasks": [],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_task_count"], 0)
        self.assertEqual(response.json()["overall_traffic_light"], "GREEN")


if __name__ == "__main__":
    unittest.main()
