import unittest

from app.domains.planning_wbs.schemas import WBSGenerationRequest
from app.domains.planning_wbs.service import PlanningWBSService
from tests.fixtures.planning_samples import wbs_request_payload


def plan_with_task(**task_overrides):
    task = {
        "name": "Implement API",
        "description": "Build endpoint",
        "mapped_requirement_ids": [1],
        "related_artifact_types": ["REQUIREMENTS_DEFINITION"],
        "completion_criteria": ["Endpoint test passes"],
    }
    task.update(task_overrides)
    return {
        "phases": [
            {
                "phase_name": "Build",
                "description": "Build phase",
                "completion_criteria": ["Build complete"],
                "work_packages": [
                    {
                        "name": "Backend",
                        "description": "Backend package",
                        "completion_criteria": ["Backend complete"],
                        "tasks": [task],
                    }
                ],
            }
        ]
    }


class PlanningWbsServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningWBSService()
        self.request = WBSGenerationRequest.model_validate(
            wbs_request_payload()
        )

    def test_contexts_sort_requirements_and_filter_repair_targets(self):
        payload = wbs_request_payload()
        payload["requirement_candidates"].reverse()
        request = WBSGenerationRequest.model_validate(payload)

        contexts = self.service.prepare_contexts(
            request,
            target_requirement_ids=[2],
            target_artifact_types=["TEST_RESULTS"],
            target_phase_names=["Analysis"],
        )

        self.assertEqual(contexts[0]["generation_mode"], "REPAIR")
        self.assertEqual(
            [item["requirement_id"] for item in contexts[0]["requirements"]],
            [2],
        )
        self.assertEqual(
            contexts[0]["project"]["required_artifacts"][0][
                "artifact_type"
            ],
            "TEST_RESULTS",
        )

    def test_finalize_filters_unknown_ids_artifacts_and_phases(self):
        plan = plan_with_task(
            mapped_requirement_ids=[1, 999],
            related_artifact_types=["REQUIREMENTS_DEFINITION", "ERD"],
        )
        plan["phases"].append(
            {
                "phase_name": "Invented",
                "description": "not allowed",
                "completion_criteria": ["done"],
                "work_packages": [],
            }
        )

        outcome = self.service.finalize(self.request, [plan])

        task = next(
            item for item in outcome.result["wbs_items"]
            if item["item_type"] == "TASK"
        )
        self.assertEqual(task["mapped_requirement_ids"], [1])
        self.assertEqual(
            [item["artifact_type"] for item in task["related_artifacts"]],
            ["REQUIREMENTS_DEFINITION"],
        )
        self.assertTrue(
            any("존재하지 않는 요구사항 ID" in warning for warning in outcome.result["warnings"])
        )
        self.assertTrue(
            any("필수 산출물이 아닌 유형" in warning for warning in outcome.result["warnings"])
        )
        self.assertTrue(
            any("방법론에 없는 단계" in warning for warning in outcome.result["warnings"])
        )

    def test_duplicate_tasks_merge_without_duplicate_coverage(self):
        payload = wbs_request_payload()
        payload["methodology"] = ["Build"]
        request = WBSGenerationRequest.model_validate(payload)
        first = plan_with_task(
            mapped_requirement_ids=[1],
            completion_criteria=["First criterion"],
        )
        second = plan_with_task(
            mapped_requirement_ids=[1, 2],
            related_artifact_types=[
                "REQUIREMENTS_DEFINITION",
                "TEST_RESULTS",
            ],
            completion_criteria=["First criterion", "Second criterion"],
        )

        outcome = self.service.finalize(request, [first, second])
        tasks = [
            item for item in outcome.result["wbs_items"]
            if item["item_type"] == "TASK"
        ]

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["mapped_requirement_ids"], [1, 2])
        self.assertEqual(
            tasks[0]["completion_criteria"],
            ["First criterion", "Second criterion"],
        )
        self.assertFalse(outcome.needs_repair)

    def test_no_required_artifacts_reports_full_artifact_coverage(self):
        payload = wbs_request_payload(requirement_count=1)
        payload["project_info"]["required_artifacts"] = []
        payload["methodology"] = ["Build"]
        request = WBSGenerationRequest.model_validate(payload)
        outcome = self.service.finalize(
            request,
            [plan_with_task(related_artifact_types=[])],
        )

        coverage = outcome.result["artifact_coverage"]
        self.assertEqual(coverage["total_required_artifacts"], 0)
        self.assertEqual(coverage["coverage_rate"], 100.0)


if __name__ == "__main__":
    unittest.main()
