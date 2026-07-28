import unittest

from app.domains.reporting.schemas import (
    DeliverableRagResponse,
    MeetingAnalysisResponse,
    RagSource,
)
from app.domains.reporting.service import ReportService
from tests.fixtures.reporting_samples import (
    final_request,
    meeting_request,
    rag_request,
    weekly_request,
)


class FakeLlm:
    def __init__(self, result=None):
        self.result = result
        self.sources = None

    def analyze_meeting(self, request):
        return self.result

    def generate_weekly_report(self, request):
        return self.result

    def generate_final_report(self, request):
        return self.result

    def answer_deliverable_rag(self, request, sources):
        self.sources = sources
        return self.result


class ReportingServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = ReportService()

    def test_meeting_fallback_extracts_actions_and_missing_links(self):
        result = self.service.analyze_meeting(meeting_request())

        self.assertEqual(result.llm_status, "FALLBACK")
        self.assertEqual(result.action_items[0].owner, "김남효")
        self.assertEqual(result.missing_owner_count, 1)
        self.assertEqual(result.missing_due_date_count, 2)
        self.assertEqual(result.risk_missing_owner_count, 1)
        self.assertEqual(result.risk_missing_link_count, 1)

    def test_meeting_with_no_signals_returns_empty_collections(self):
        result = self.service.analyze_meeting(
            meeting_request(text="Routine status was shared.")
        )
        self.assertEqual(result.action_items, [])
        self.assertEqual(result.issue_risk_changes, [])
        self.assertEqual(result.missing_owner_count, 0)

    def test_successful_meeting_llm_result_is_returned_without_fallback(self):
        expected = MeetingAnalysisResponse.model_validate(
            {
                "project_id": 7,
                "meeting_summary": "LLM summary",
                "decision_logs": [],
                "action_items": [],
                "issue_risk_changes": [],
                "missing_owner_count": 0,
                "missing_due_date_count": 0,
                "generated_at": "2026-07-28T00:00:00",
                "llm_status": "SUCCEEDED",
            }
        )
        self.service.llm_service = FakeLlm(expected)

        result = self.service.analyze_meeting(
            meeting_request(enable_llm=True)
        )
        self.assertIs(result, expected)

    def test_weekly_fallback_calculates_completed_delayed_and_risks(self):
        result = self.service.generate_weekly_report(weekly_request())

        self.assertEqual(result.progress_summary, "평균 진행률 70.0%")
        self.assertEqual(result.completed_work, ["Completed API"])
        self.assertEqual(result.delayed_work, ["Delayed UI"])
        self.assertIn("API dependency", result.risk_summary)
        self.assertIn(
            "담당자 미지정 작업: Delayed UI", result.risk_summary
        )
        self.assertEqual(result.llm_status, "FALLBACK")

    def test_weekly_empty_wbs_uses_zero_progress(self):
        request = weekly_request()
        request.wbs_tasks = []
        request.open_risks = []
        result = self.service.generate_weekly_report(request)

        self.assertEqual(result.progress_summary, "평균 진행률 0.0%")
        self.assertEqual(result.completed_work, [])
        self.assertEqual(result.delayed_work, [])

    def test_final_fallback_separates_done_and_incomplete(self):
        result = self.service.generate_final_report(final_request())

        self.assertEqual(result.achievement_summary, ["Backend"])
        self.assertEqual(result.incomplete_items, ["Frontend"])
        self.assertIn("완료 항목 1건", result.final_summary)
        self.assertEqual(result.llm_status, "FALLBACK")

    def test_rag_matches_only_documents_with_question_keywords(self):
        result = self.service.answer_deliverable_rag(rag_request())

        self.assertEqual(len(result.sources), 1)
        self.assertEqual(result.sources[0].document_id, "DOC-1")
        self.assertEqual(result.sources[0].page, 2)
        self.assertIn("근거 문서", result.answer)

    def test_rag_without_match_does_not_invent_source(self):
        result = self.service.answer_deliverable_rag(
            rag_request(question="Budget amount?")
        )
        self.assertEqual(result.sources, [])
        self.assertIn("찾지 못했습니다", result.answer)

    def test_rag_llm_receives_only_rule_matched_sources(self):
        fake = FakeLlm(
            DeliverableRagResponse(
                project_id=7,
                answer="Grounded answer",
                sources=[],
                generated_at="2026-07-28T00:00:00",
                llm_status="SUCCEEDED",
            )
        )
        self.service.llm_service = fake
        result = self.service.answer_deliverable_rag(
            rag_request(enable_llm=True)
        )

        self.assertEqual(result.answer, "Grounded answer")
        self.assertEqual(len(fake.sources), 1)
        self.assertIsInstance(fake.sources[0], RagSource)


if __name__ == "__main__":
    unittest.main()
