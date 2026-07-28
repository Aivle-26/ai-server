import unittest

from app.domains.reporting.graph import ReportGraph
from tests.fixtures.reporting_samples import (
    final_request,
    meeting_request,
    rag_request,
    weekly_request,
)


class ReportingGraphTest(unittest.TestCase):
    def setUp(self):
        self.graph = ReportGraph()

    def test_graph_delegates_each_supported_flow(self):
        meeting = self.graph.invoke(meeting_request())
        weekly = self.graph.generate_weekly_report(weekly_request())
        final = self.graph.generate_final_report(final_request())
        rag = self.graph.query_deliverable_rag(rag_request())

        self.assertEqual(meeting.project_id, 7)
        self.assertEqual(weekly.project_id, 7)
        self.assertEqual(final.project_id, 7)
        self.assertEqual(rag.project_id, 7)
        self.assertEqual(
            self.graph.answer_deliverable_rag(rag_request()).answer,
            rag.answer,
        )


if __name__ == "__main__":
    unittest.main()
