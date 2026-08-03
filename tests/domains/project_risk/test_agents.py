import unittest

from app.domains.project_risk.agents.assignment_agent import AssignmentAgent
from app.domains.project_risk.agents.planning_agent import PlanningAgent
from app.domains.project_risk.agents.report_agent import ReportAgent
from app.domains.project_risk.agents.risk_agent import RiskAgent


class ProjectRiskAgentTest(unittest.TestCase):
    def test_planning_agent_builds_requirement_and_four_ordered_tasks(self):
        result = PlanningAgent().analyze(
            {
                "project": {"project_id": 7},
                "planning_events": [
                    {
                        "normalized_event_id": 10,
                        "source_type": "JIRA",
                        "title": "Audit log",
                        "content": "시스템 로그와 접근 권한을 기록한다.",
                        "priority": "HIGH",
                    }
                ],
            }
        )

        self.assertEqual(result["requirement_count"], 1)
        self.assertEqual(result["wbs_count"], 4)
        self.assertEqual(
            result["requirements"][0]["requirement_type"],
            "NON_FUNCTIONAL",
        )
        self.assertEqual(
            [item["task_order"] for item in result["wbs_tasks"]],
            [1, 2, 3, 4],
        )
        self.assertTrue(
            all(
                item["requirement_code"] == "REQ-001"
                for item in result["wbs_tasks"]
            )
        )

    def test_planning_agent_handles_empty_events(self):
        result = PlanningAgent().analyze(
            {"project": {"project_id": 7}, "planning_events": []}
        )
        self.assertEqual(result["requirements"], [])
        self.assertEqual(result["wbs_tasks"], [])

    def test_risk_agent_classifies_sources_levels_and_actions(self):
        result = RiskAgent().analyze(
            {
                "project": {"project_id": 7},
                "risk_events": [
                    {
                        "normalized_event_id": 1,
                        "source_type": "SLACK",
                        "title": "Blocked",
                        "content": "긴급 blocker",
                        "priority": "CRITICAL",
                        "status": "BLOCKED",
                    },
                    {
                        "normalized_event_id": 2,
                        "source_type": "JIRA",
                        "title": "API error",
                        "content": "오류 재현",
                        "priority": "HIGH",
                        "status": "OPEN",
                    },
                ],
            }
        )

        self.assertEqual(result["risk_count"], 2)
        self.assertEqual(result["risks"][0]["risk_type"], "COMMUNICATION")
        self.assertEqual(result["risks"][0]["risk_level"], "HIGH")
        self.assertEqual(result["risks"][1]["risk_type"], "QUALITY")
        self.assertTrue(result["risks"][1]["recommended_actions"])

    def test_report_agent_handles_empty_and_mixed_events(self):
        agent = ReportAgent()
        empty = agent.generate(
            {
                "project": {
                    "project_name": "AIPM",
                    "status": "PLANNING",
                },
                "report_events": [],
                "completed_events": [],
                "in_progress_events": [],
            }
        )
        mixed = agent.generate(
            {
                "project": {
                    "project_name": "AIPM",
                    "status": "ACTIVE",
                },
                "report_events": [{}, {}, {}],
                "completed_events": [{}],
                "in_progress_events": [{}],
            }
        )

        self.assertEqual(empty["completion_rate"], 0)
        self.assertEqual(mixed["completion_rate"], 33.33)
        self.assertIn("완료 1건", mixed["summary_text"])

    def test_assignment_agent_role_prediction_covers_all_domains(self):
        agent = AssignmentAgent()
        cases = {
            "Spring API server": "BACKEND",
            "React UI screen": "FRONTEND",
            "LangGraph RAG": "AI",
            "Generic task": "BACKEND",
        }
        for task, expected in cases.items():
            with self.subTest(task=task):
                self.assertEqual(agent._predict_role(task), expected)


if __name__ == "__main__":
    unittest.main()
