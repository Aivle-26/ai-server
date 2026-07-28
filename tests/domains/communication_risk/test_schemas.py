from datetime import datetime
import unittest

from pydantic import ValidationError

from app.domains.communication_risk.schemas import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
    SlackMessageThreadInput,
)


def message_payload(**overrides):
    payload = {
        "channel_id": "C-1",
        "channel_name": "delivery",
        "message_ts": "2026-07-27T10:00:00Z",
        "user_id": "U-1",
        "message_text": "Please review this task.",
    }
    payload.update(overrides)
    return payload


class CommunicationRiskSchemaTest(unittest.TestCase):
    def test_message_defaults_and_datetime_parsing(self):
        message = SlackMessageThreadInput.model_validate(message_payload())

        self.assertIsInstance(message.message_ts, datetime)
        self.assertEqual(message.reply_count, 0)
        self.assertEqual(message.mention_count, 0)
        self.assertEqual(message.file_count, 0)

    def test_message_rejects_blank_text_and_negative_counts(self):
        for overrides in (
            {"message_text": ""},
            {"reply_count": -1},
            {"mention_count": -1},
            {"file_count": -1},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(
                ValidationError
            ):
                SlackMessageThreadInput.model_validate(
                    message_payload(**overrides)
                )

    def test_request_requires_positive_project_and_messages(self):
        for payload in (
            {"project_id": 0, "messages": [message_payload()]},
            {"project_id": 1, "messages": []},
        ):
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                CommunicationRiskRequest.model_validate(payload)

    def test_response_rejects_unknown_level_and_empty_reasons(self):
        base = {
            "project_id": 1,
            "project_name": None,
            "communication_risk_level": "LOW",
            "reasons": ["No signal"],
            "evidence_messages": [],
            "recommended_action": "Continue monitoring",
            "metrics": {
                "recent_7d_message_count": 0,
                "previous_7d_message_count": 0,
                "activity_change_percent": None,
                "long_unanswered_count": 0,
            },
            "analysis_window": {
                "start": "2026-07-20T00:00:00",
                "end": "2026-07-27T00:00:00",
            },
            "llm_status": "DISABLED",
        }
        for changes in (
            {"communication_risk_level": "CRITICAL"},
            {"reasons": []},
            {"llm_status": "UNKNOWN"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                CommunicationRiskResponse.model_validate({**base, **changes})


if __name__ == "__main__":
    unittest.main()
