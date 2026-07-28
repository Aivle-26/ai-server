from datetime import datetime
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class FakeGraph:
    def __init__(self):
        self.request = None

    def invoke(self, request):
        self.request = request
        return {
            "project_id": request["project_id"],
            "project_name": request["project_name"],
            "communication_risk_level": "LOW",
            "reasons": ["No risk signal"],
            "evidence_messages": [],
            "recommended_action": "Continue monitoring",
            "metrics": {
                "recent_7d_message_count": 1,
                "previous_7d_message_count": 0,
                "activity_change_percent": None,
                "long_unanswered_count": 0,
            },
            "analysis_window": {
                "start": "2026-07-21T12:00:00",
                "end": "2026-07-28T12:00:00",
            },
            "llm_status": "DISABLED",
        }


class CommunicationRiskRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_router_serializes_messages_and_returns_contract(self):
        graph = FakeGraph()
        payload = {
            "project_id": 7,
            "project_name": "AIPM",
            "analysis_end": "2026-07-28T12:00:00",
            "messages": [
                {
                    "channel_id": "C-1",
                    "channel_name": "delivery",
                    "message_ts": "2026-07-27T12:00:00",
                    "user_id": "U-1",
                    "message_text": "Status update",
                }
            ],
            "enable_llm": False,
        }
        with patch(
            "app.domains.communication_risk.router._graph", graph
        ):
            response = self.client.post(
                "/api/v1/risk/communication/analyze", json=payload
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["communication_risk_level"], "LOW")
        self.assertIsInstance(graph.request["analysis_end"], str)
        self.assertIsInstance(graph.request["messages"][0]["message_ts"], str)

    def test_router_rejects_invalid_message_without_invoking_graph(self):
        graph = FakeGraph()
        with patch(
            "app.domains.communication_risk.router._graph", graph
        ):
            response = self.client.post(
                "/api/v1/risk/communication/analyze",
                json={
                    "project_id": 7,
                    "messages": [
                        {
                            "channel_id": "C-1",
                            "channel_name": "delivery",
                            "message_ts": datetime.now().isoformat(),
                            "user_id": "U-1",
                            "message_text": "",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(graph.request)


if __name__ == "__main__":
    unittest.main()
