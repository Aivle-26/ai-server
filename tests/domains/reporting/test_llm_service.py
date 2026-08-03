import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.domains.reporting.llm_service import ReportLlmService
from app.domains.reporting.schemas import RagSource
from tests.fixtures.reporting_samples import (
    final_request,
    meeting_request,
    rag_request,
    weekly_request,
)


class ReportingLlmServiceTest(unittest.TestCase):
    def test_parse_json_content_accepts_plain_and_fenced_json(self):
        service = ReportLlmService()
        self.assertEqual(service._parse_json_content('{"value": 1}'), {"value": 1})
        self.assertEqual(
            service._parse_json_content('```json\n{"value": 2}\n```'),
            {"value": 2},
        )
        with self.assertRaises(ValueError):
            service._parse_json_content("not-json")

    def test_missing_key_returns_none_without_openai_client(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("openai.OpenAI") as client,
        ):
            service = ReportLlmService()
            result = service._call_llm_json("prompt")
        self.assertIsNone(result)
        client.assert_not_called()

    def test_chat_completion_is_parsed_and_uses_deterministic_temperature(self):
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='```json\n{"answer": "ok"}\n```'
                    )
                )
            ]
        )
        client = MagicMock()
        client.chat.completions.create.return_value = completion

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch("openai.OpenAI", return_value=client),
        ):
            service = ReportLlmService()
            result = service._call_llm_json("prompt")

        self.assertEqual(result, {"answer": "ok"})
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["temperature"], 0.2)
        self.assertEqual(request["messages"][1]["content"], "prompt")

    def test_client_api_or_json_failure_returns_none(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch("openai.OpenAI", side_effect=TimeoutError("timeout")),
        ):
            self.assertIsNone(ReportLlmService()._call_llm_json("prompt"))

        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="not-json")
                )
            ]
        )
        client = MagicMock()
        client.chat.completions.create.return_value = completion
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch("openai.OpenAI", return_value=client),
        ):
            self.assertIsNone(ReportLlmService()._call_llm_json("prompt"))

    def test_meeting_structured_data_is_validated_and_counted(self):
        service = ReportLlmService()
        service._call_llm_json = MagicMock(
            return_value={
                "meeting_summary": "Summary",
                "decision_logs": [],
                "action_items": [
                    {
                        "action_item": "Task",
                        "owner": None,
                        "due_date": None,
                        "status": "TODO",
                    }
                ],
                "issue_risk_changes": [
                    {
                        "risk_title": "담당자 미지정",
                        "risk_type": "인력/역할 리스크",
                        "risk_level": "MEDIUM",
                        "reason": "담당자가 없다",
                    }
                ],
            }
        )

        result = service.analyze_meeting(meeting_request(enable_llm=True))

        self.assertEqual(result.llm_status, "SUCCEEDED")
        self.assertEqual(result.missing_owner_count, 1)
        self.assertEqual(result.risk_missing_owner_count, 1)
        self.assertEqual(result.risk_missing_link_count, 1)
        prompt = service._call_llm_json.call_args.args[0]
        self.assertIn("source.excerpt", prompt)
        self.assertIn("입력 회의록에 없는 내용은 절대 추측", prompt)

    def test_invalid_structured_data_returns_none_for_fallback(self):
        service = ReportLlmService()
        service._call_llm_json = MagicMock(
            return_value={
                "meeting_summary": "Summary",
                "action_items": [{"action_item": "Task", "status": "BAD"}],
            }
        )
        self.assertIsNone(
            service.analyze_meeting(meeting_request(enable_llm=True))
        )

    def test_weekly_final_and_rag_llm_outputs_use_request_identity(self):
        service = ReportLlmService()
        service._call_llm_json = MagicMock(
            return_value={
                "progress_summary": "Progress",
                "completed_work": [],
                "delayed_work": [],
                "risk_summary": [],
                "next_week_plan": [],
                "report_draft": "Draft",
            }
        )
        weekly = service.generate_weekly_report(
            weekly_request(enable_llm=True)
        )
        self.assertEqual(weekly.project_id, 7)
        self.assertEqual(weekly.llm_status, "SUCCEEDED")

        service._call_llm_json.return_value = {
            "final_summary": "Final",
            "achievement_summary": [],
            "incomplete_items": [],
            "remaining_risk_summary": [],
            "final_report_draft": "Draft",
        }
        final = service.generate_final_report(
            final_request(enable_llm=True)
        )
        self.assertEqual(final.project_id, 7)

        service._call_llm_json.return_value = {"answer": "Grounded"}
        sources = [
            RagSource(
                deliverable_id="D-1",
                document_id="DOC-1",
                document_name="requirements.txt",
                excerpt="API status",
            )
        ]
        rag = service.answer_deliverable_rag(
            rag_request(enable_llm=True), sources
        )
        self.assertEqual(rag.answer, "Grounded")
        self.assertEqual(rag.sources, sources)


if __name__ == "__main__":
    unittest.main()
