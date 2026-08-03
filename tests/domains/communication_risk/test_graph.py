from datetime import datetime, timedelta
import unittest

from fastapi.testclient import TestClient

from app.domains.communication_risk.graph import CommunicationRiskGraph
from app.main import app


ANALYSIS_END = datetime(2026, 7, 15, 12, 0, 0)


def message(
    timestamp: datetime,
    text: str,
    *,
    reply_count: int = 0,
    mention_count: int = 0,
    reaction_summary: str = "",
) -> dict:
    return {
        "channel_id": "C-PROJECT",
        "channel_name": "project-backend",
        "message_ts": timestamp.isoformat(),
        "thread_ts": None,
        "user_id": "U-DEV",
        "message_text": text,
        "reply_count": reply_count,
        "mention_count": mention_count,
        "reaction_summary": reaction_summary,
        "file_count": 0,
    }


class FakeDecisionService:
    def decide(self, facts, project_name, enabled, fallback):
        return {
            "communication_risk_level": "HIGH",
            "reasons": ["배포 차단 메시지가 장기 미응답 상태입니다."],
            "evidence_message_ts": [facts["candidate_messages"][0]["message_ts"]],
            "recommended_action": "담당자에게 즉시 상태를 확인하세요.",
        }, "SUCCEEDED"


class CommunicationRiskGraphTest(unittest.TestCase):
    def invoke(self, messages, *, enable_llm=False):
        return CommunicationRiskGraph().invoke({
            "project_id": 1,
            "project_name": "AIVLE PM Platform",
            "analysis_end": ANALYSIS_END.isoformat(),
            "messages": messages,
            "enable_llm": enable_llm,
        })

    def test_healthy_project_is_low(self):
        messages = [
            message(ANALYSIS_END - timedelta(days=index + 1), "진행 상황 공유", reply_count=1)
            for index in range(10)
        ]
        result = self.invoke(messages)
        self.assertEqual(result["communication_risk_level"], "LOW")
        self.assertEqual(result["metrics"]["long_unanswered_count"], 0)

    def test_activity_drop_is_medium(self):
        messages = [
            message(ANALYSIS_END - timedelta(days=8, hours=index), "지난주 진행 상황 공유")
            for index in range(10)
        ]
        messages.append(message(ANALYSIS_END - timedelta(days=1), "이번 주 진행 상황 공유"))
        result = self.invoke(messages)
        self.assertEqual(result["communication_risk_level"], "MEDIUM")
        self.assertLess(result["metrics"]["activity_change_percent"], -50)

    def test_long_unanswered_request_is_medium(self):
        result = self.invoke([
            message(
                ANALYSIS_END - timedelta(hours=30),
                "담당자 확인 부탁드립니다.",
                mention_count=1,
            )
        ])
        self.assertEqual(result["communication_risk_level"], "MEDIUM")
        self.assertEqual(result["metrics"]["long_unanswered_count"], 1)

    def test_llm_decision_is_used_for_context_risk(self):
        graph = CommunicationRiskGraph(decision_service=FakeDecisionService())
        result = graph.invoke({
            "project_id": 1,
            "project_name": "AIVLE PM Platform",
            "analysis_end": ANALYSIS_END.isoformat(),
            "enable_llm": True,
            "messages": [message(
                ANALYSIS_END - timedelta(hours=30),
                "배포가 blocker 상태입니다. 담당자 확인 부탁드립니다.",
                mention_count=1,
            )],
        })
        self.assertEqual(result["communication_risk_level"], "HIGH")
        self.assertEqual(result["llm_status"], "SUCCEEDED")
        self.assertIn("배포 차단", result["reasons"][0])

    def test_fastapi_returns_simple_contract(self):
        response = TestClient(app).post(
            "/api/v1/risk/communication/analyze",
            json={
                "project_id": 7,
                "analysis_end": ANALYSIS_END.isoformat(),
                "enable_llm": False,
                "messages": [message(
                    ANALYSIS_END - timedelta(hours=30),
                    "담당자 확인 부탁드립니다.",
                    mention_count=1,
                )],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["communication_risk_level"], "MEDIUM")


if __name__ == "__main__":
    unittest.main()
