from datetime import datetime, timedelta, timezone
import unittest

from app.domains.communication_risk.risk_service import (
    CommunicationRiskService,
    _to_naive_datetime,
)


END = datetime(2026, 7, 28, 12, 0, 0)


def message(timestamp, text="Status update", **overrides):
    payload = {
        "channel_id": "C-1",
        "channel_name": "delivery",
        "message_ts": timestamp,
        "thread_ts": None,
        "user_id": "U-1",
        "message_text": text,
        "reply_count": 0,
        "mention_count": 0,
        "reaction_summary": "",
        "file_count": 0,
    }
    payload.update(overrides)
    return payload


class CommunicationRiskServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = CommunicationRiskService()

    def test_timezone_values_are_normalized_to_naive_utc(self):
        value = datetime(
            2026, 7, 28, 21, 0, tzinfo=timezone(timedelta(hours=9))
        )
        self.assertEqual(_to_naive_datetime(value), END)
        self.assertEqual(
            _to_naive_datetime("2026-07-28T12:00:00Z"), END
        )

    def test_acknowledged_request_is_not_long_unanswered(self):
        facts = self.service.build_facts(
            [
                message(
                    END - timedelta(hours=30),
                    "@owner please review?",
                    mention_count=1,
                    reaction_summary="eyes:1",
                )
            ],
            END,
        )

        self.assertEqual(facts["metrics"]["long_unanswered_count"], 0)
        self.assertEqual(len(facts["candidate_messages"]), 0)

    def test_previous_window_zero_keeps_change_percent_none(self):
        facts = self.service.build_facts(
            [message(END - timedelta(days=1))], END
        )

        self.assertEqual(facts["metrics"]["recent_7d_message_count"], 1)
        self.assertEqual(facts["metrics"]["previous_7d_message_count"], 0)
        self.assertIsNone(facts["metrics"]["activity_change_percent"])

    def test_contextual_unanswered_request_is_high(self):
        facts = self.service.build_facts(
            [
                message(
                    END - timedelta(hours=30),
                    "Deployment blocker, please review?",
                    mention_count=1,
                )
            ],
            END,
        )
        decision = self.service.fallback_decision(facts)

        self.assertEqual(decision["communication_risk_level"], "HIGH")
        self.assertEqual(len(decision["evidence_message_ts"]), 1)
        self.assertLessEqual(len(decision["reasons"]), 3)

    def test_response_ignores_evidence_not_present_in_candidates(self):
        facts = self.service.build_facts(
            [
                message(
                    END - timedelta(hours=30),
                    "Please review?",
                    mention_count=1,
                )
            ],
            END,
        )
        decision = {
            "communication_risk_level": "MEDIUM",
            "reasons": ["One unanswered request"],
            "evidence_message_ts": [
                facts["candidate_messages"][0]["message_ts"],
                "2099-01-01T00:00:00",
            ],
            "recommended_action": "Review it",
        }

        response = self.service.build_response(
            7, "AIPM", facts, decision, "DISABLED"
        )
        self.assertEqual(len(response["evidence_messages"]), 1)
        self.assertNotIn("is_long_unanswered", response["evidence_messages"][0])


if __name__ == "__main__":
    unittest.main()
