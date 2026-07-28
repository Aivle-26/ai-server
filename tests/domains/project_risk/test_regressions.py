from datetime import date
import unittest

from fastapi.testclient import TestClient

from app.domains.project_risk.services.schedule_risk_service import (
    analyze_schedule_task,
)
from app.main import app


class ProjectRiskRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_duplicate_approved_artifact_counts_once(self):
        response = self.client.post(
            "/api/v1/risk/artifact-status",
            json={
                "project_id": 7,
                "required_artifacts": ["Requirements"],
                "registered_artifacts": [
                    {
                        "artifact_name": "Requirements",
                        "artifact_type": "DOCUMENT",
                        "version": "1.0",
                        "approved": True,
                    },
                    {
                        "artifact_name": "Requirements",
                        "artifact_type": "DOCUMENT",
                        "version": "1.1",
                        "approved": True,
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["approved_count"], 1)
        self.assertEqual(response.json()["approval_rate"], 100.0)

    def test_completed_overdue_task_has_zero_risk(self):
        result = analyze_schedule_task(
            {
                "task_id": 1,
                "task_name": "Done",
                "start_date": date(2026, 7, 1),
                "due_date": date(2026, 7, 10),
                "progress": 0,
                "status": "DONE",
            },
            date(2026, 7, 28),
        )

        self.assertEqual(result["risk_score"], 0)
        self.assertEqual(result["traffic_light"], "GREEN")
        self.assertEqual(result["overdue_days"], 18)


if __name__ == "__main__":
    unittest.main()
