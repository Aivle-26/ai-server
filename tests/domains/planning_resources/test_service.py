import unittest

from app.domains.planning_resources.llm_service import (
    GeneratedRequiredSkill,
    GeneratedResourcePlan,
    GeneratedTaskResourceEstimate,
)
from app.domains.planning_resources.schemas import PlanningResourceRequest
from app.domains.planning_resources.service import PlanningResourceService
from tests.fixtures.planning_samples import resource_request_payload


def estimate(
    wbs_id,
    role="BACKEND_DEVELOPER",
    skills=None,
    days=2.0,
):
    return GeneratedTaskResourceEstimate(
        wbs_id=wbs_id,
        required_role_code=role,
        required_skills=skills or [],
        estimated_person_days=days,
        estimation_reason="Task complexity",
    )


class PlanningResourceServiceTest(unittest.TestCase):
    def setUp(self):
        self.request = PlanningResourceRequest.model_validate(
            resource_request_payload()
        )
        self.service = PlanningResourceService()

    def test_context_includes_allowed_codes_but_not_member_capacity(self):
        contexts = self.service.prepare_contexts(self.request)

        self.assertEqual(len(contexts), 1)
        self.assertIn(
            "BACKEND_DEVELOPER", contexts[0]["allowed_role_codes"]
        )
        self.assertIn("SPRING_BOOT", contexts[0]["allowed_skill_codes"])
        self.assertNotIn("project_members", contexts[0])
        self.assertNotIn("start_date", contexts[0]["tasks"][0])

    def test_invalid_llm_role_and_skill_are_removed_with_warnings(self):
        plans = [
            GeneratedResourcePlan(
                task_estimates=[
                    estimate(
                        3,
                        role="ALIEN",
                        skills=[
                            GeneratedRequiredSkill(
                                skill_code="COBOL",
                                minimum_proficiency_level=5,
                            )
                        ],
                    ),
                    estimate(6),
                ]
            )
        ]

        result = self.service.build_recommendation(self.request, plans)
        assignment = next(
            item for item in result["assignments"] if item["wbs_id"] == 3
        )

        self.assertEqual(assignment["required_role_code"], "UNSPECIFIED")
        self.assertEqual(assignment["required_skills"], [])
        self.assertIn(3, result["unassigned_wbs_ids"])
        self.assertTrue(any("ALIEN" in item for item in result["warnings"]))
        self.assertTrue(any("COBOL" in item for item in result["warnings"]))

    def test_missing_estimate_uses_one_person_day_and_warns(self):
        plans = [
            GeneratedResourcePlan(task_estimates=[estimate(6)])
        ]
        result = self.service.build_recommendation(self.request, plans)
        assignment = next(
            item for item in result["assignments"] if item["wbs_id"] == 3
        )

        self.assertEqual(assignment["estimated_person_days"], 1.0)
        self.assertEqual(assignment["estimated_hours"], 8.0)
        self.assertTrue(
            any("공수 추정이 누락" in item for item in result["warnings"])
        )

    def test_duplicate_estimates_keep_first_and_skill_list_deduplicates(self):
        duplicate_skills = [
            GeneratedRequiredSkill(
                skill_code="SPRING_BOOT", minimum_proficiency_level=3
            ),
            GeneratedRequiredSkill(
                skill_code="SPRING_BOOT", minimum_proficiency_level=5
            ),
        ]
        plans = [
            GeneratedResourcePlan(
                task_estimates=[
                    estimate(3, days=1),
                    estimate(3, days=9),
                    estimate(6, skills=duplicate_skills),
                ]
            )
        ]

        estimate_map = self.service._estimate_map(plans)
        normalized = self.service._required_skills(duplicate_skills)

        self.assertEqual(estimate_map[3].estimated_person_days, 1)
        self.assertEqual(
            normalized,
            [
                {
                    "skill_code": "SPRING_BOOT",
                    "minimum_proficiency_level": 3,
                }
            ],
        )

    def test_weekend_only_task_has_no_assignment_and_warning(self):
        payload = resource_request_payload()
        payload["wbs_tasks"] = [
            {
                "wbs_id": 3,
                "wbs_name": "Weekend task",
                "description": "Weekend only",
                "start_date": "2026-08-08",
                "end_date": "2026-08-09",
            }
        ]
        request = PlanningResourceRequest.model_validate(payload)
        plans = [
            GeneratedResourcePlan(task_estimates=[estimate(3)])
        ]

        result = self.service.build_recommendation(request, plans)

        self.assertEqual(result["unassigned_wbs_ids"], [3])
        self.assertTrue(any("평일이 없어" in item for item in result["warnings"]))

    def test_unknown_capability_member_is_not_ranked_and_adds_warning(self):
        payload = resource_request_payload()
        unknown_member_id = payload["project_members"][0]["project_member_id"]
        payload["project_members"][0]["roles"] = []
        payload["project_members"][0]["skills"] = []
        request = PlanningResourceRequest.model_validate(payload)
        plans = [
            GeneratedResourcePlan(
                task_estimates=[estimate(task.wbs_id) for task in request.wbs_tasks]
            )
        ]

        result = self.service.build_recommendation(request, plans)
        assigned_member_ids = {
            member["project_member_id"]
            for assignment in result["assignments"]
            for member in assignment["recommended_members"]
        }

        self.assertNotIn(unknown_member_id, assigned_member_ids)
        self.assertIn(
            "역량 정보가 없어 자동 배정에서 제외된 팀원이 1명 있습니다.",
            result["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
