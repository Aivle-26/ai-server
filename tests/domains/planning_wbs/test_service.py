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
        "required_skills": ["BACKEND_DEVELOPMENT"],
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

    def test_leaf_task_keeps_required_skill_and_parents_do_not(self):
        outcome = self.service.finalize(self.request, [plan_with_task()])
        phase = next(
            item for item in outcome.result["wbs_items"]
            if item["item_type"] == "PHASE"
        )
        work_package = next(
            item for item in outcome.result["wbs_items"]
            if item["item_type"] == "WORK_PACKAGE"
        )
        task = next(
            item for item in outcome.result["wbs_items"]
            if item["item_type"] == "TASK"
        )

        self.assertEqual(phase["required_skills"], [])
        self.assertEqual(work_package["required_skills"], [])
        self.assertEqual(task["required_skills"], ["BACKEND_DEVELOPMENT"])

    def test_independent_roles_left_on_leaf_task_add_warning(self):
        outcome = self.service.finalize(
            self.request,
            [plan_with_task(required_skills=[
                "BACKEND_DEVELOPMENT",
                "FRONTEND_DEVELOPMENT",
            ])],
        )

        self.assertTrue(any(
            "독립적인 실행 역할" in warning
            for warning in outcome.result["warnings"]
        ))

    def test_supporting_skill_pairs_do_not_add_split_warning(self):
        supporting_pairs = [
            ["BACKEND_DEVELOPMENT", "SECURITY"],
            ["DATA_ENGINEERING", "DATABASE"],
            ["FRONTEND_DEVELOPMENT", "ACCESSIBILITY"],
        ]

        for required_skills in supporting_pairs:
            with self.subTest(required_skills=required_skills):
                outcome = self.service.finalize(
                    self.request,
                    [plan_with_task(required_skills=required_skills)],
                )
                self.assertFalse(any(
                    "독립적인 실행 역할" in warning
                    for warning in outcome.result["warnings"]
                ))

    def test_new_independent_roles_left_on_leaf_task_add_warning(self):
        for required_skills in (
            ["BACKEND_DEVELOPMENT", "MOBILE_DEVELOPMENT"],
            ["DATA_ENGINEERING", "FRONTEND_DEVELOPMENT"],
        ):
            with self.subTest(required_skills=required_skills):
                outcome = self.service.finalize(
                    self.request,
                    [plan_with_task(required_skills=required_skills)],
                )
                self.assertTrue(any(
                    "독립적인 실행 역할" in warning
                    for warning in outcome.result["warnings"]
                ))

    def test_backend_and_frontend_tasks_remain_separate_and_keep_requirements(self):
        plan = plan_with_task(
            name="변경 영향 분석 API 및 재계산 로직 구현",
            mapped_requirement_ids=[1, 2],
            required_skills=["BACKEND_DEVELOPMENT"],
        )
        tasks = plan["phases"][0]["work_packages"][0]["tasks"]
        tasks.append({
            "name": "변경 영향 분석 결과 화면 구현",
            "description": "변경 영향 분석 결과를 화면에 표시한다.",
            "mapped_requirement_ids": [1, 2],
            "related_artifact_types": [],
            "completion_criteria": ["분석 결과 화면 표시 완료"],
            "required_skills": ["FRONTEND_DEVELOPMENT"],
        })

        outcome = self.service.finalize(self.request, [plan])
        leaf_tasks = [
            item for item in outcome.result["wbs_items"]
            if item["item_type"] == "TASK"
        ]

        self.assertEqual(len(leaf_tasks), 2)
        self.assertEqual(
            [item["required_skills"] for item in leaf_tasks],
            [["BACKEND_DEVELOPMENT"], ["FRONTEND_DEVELOPMENT"]],
        )
        self.assertTrue(all(
            item["mapped_requirement_ids"] == [1, 2]
            for item in leaf_tasks
        ))


if __name__ == "__main__":
    unittest.main()
