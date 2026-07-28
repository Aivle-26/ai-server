import os
import unittest
from unittest.mock import MagicMock, patch

from app.domains.communication_risk.llm_service import (
    CommunicationLLMDecisionService,
    CommunicationRiskDecision,
)


FACTS = {
    "metrics": {
        "recent_7d_message_count": 1,
        "previous_7d_message_count": 5,
        "activity_change_percent": -80.0,
        "long_unanswered_count": 1,
    },
    "activity_drop": True,
    "candidate_messages": [
        {
            "message_ts": "2026-07-27T00:00:00",
            "message_text": "blocked",
        }
    ],
}
FALLBACK = {
    "communication_risk_level": "MEDIUM",
    "reasons": ["Fallback"],
    "evidence_message_ts": [],
    "recommended_action": "Review",
}


class CommunicationLlmServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = CommunicationLLMDecisionService()

    def test_disabled_does_not_construct_client(self):
        with patch(
            "app.domains.communication_risk.llm_service.ChatOpenAI"
        ) as client:
            result, status = self.service.decide(
                FACTS, "AIPM", False, FALLBACK
            )

        self.assertIs(result, FALLBACK)
        self.assertEqual(status, "DISABLED")
        client.assert_not_called()

    def test_missing_key_returns_fallback_without_client(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "app.domains.communication_risk.llm_service.ChatOpenAI"
            ) as client,
        ):
            result, status = self.service.decide(
                FACTS, "AIPM", True, FALLBACK
            )

        self.assertIs(result, FALLBACK)
        self.assertEqual(status, "SKIPPED_NO_API_KEY")
        client.assert_not_called()

    def test_success_filters_unknown_evidence_timestamps(self):
        structured = MagicMock()
        structured.invoke.return_value = CommunicationRiskDecision(
            communication_risk_level="HIGH",
            reasons=["Blocking message"],
            evidence_message_ts=[
                "2026-07-27T00:00:00",
                "2099-01-01T00:00:00",
            ],
            recommended_action="Escalate",
        )
        client = MagicMock()
        client.with_structured_output.return_value = structured

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.communication_risk.llm_service.ChatOpenAI",
                return_value=client,
            ) as constructor,
        ):
            result, status = self.service.decide(
                FACTS, "AIPM", True, FALLBACK
            )

        self.assertEqual(status, "SUCCEEDED")
        self.assertEqual(
            result["evidence_message_ts"], ["2026-07-27T00:00:00"]
        )
        constructor.assert_called_once()

    def test_client_or_api_failure_returns_fallback(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.communication_risk.llm_service.ChatOpenAI",
                side_effect=TimeoutError("timeout"),
            ),
        ):
            result, status = self.service.decide(
                FACTS, None, True, FALLBACK
            )

        self.assertIs(result, FALLBACK)
        self.assertEqual(status, "FALLBACK")


if __name__ == "__main__":
    unittest.main()
