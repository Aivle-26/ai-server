import unittest

from pydantic import ValidationError

from app.domains.planning_resources.schemas import (
    PlanningResourceRequest,
    ProjectMemberCandidate,
)
from tests.fixtures.planning_samples import resource_request_payload


class PlanningResourceSchemaTest(unittest.TestCase):
    def test_member_roles_and_skill_codes_are_normalized(self):
        member = ProjectMemberCandidate.model_validate(
            {
                "project_member_id": 1,
                "roles": [" backend_developer ", "BACKEND_DEVELOPER"],
                "skills": [
                    {
                        "skill_code": " spring_boot ",
                        "proficiency_level": 4,
                    }
                ],
            }
        )

        self.assertEqual(member.roles, ["BACKEND_DEVELOPER"])
        self.assertEqual(member.skills[0].skill_code, "SPRING_BOOT")

    def test_request_rejects_invalid_task_dates_and_blank_text(self):
        for changes in (
            {"end_date": "2026-08-01"},
            {"wbs_name": " "},
            {"description": ""},
        ):
            payload = resource_request_payload()
            payload["wbs_tasks"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                PlanningResourceRequest.model_validate(payload)

    def test_member_rejects_duplicate_skills_and_invalid_allocation(self):
        duplicate_skill = resource_request_payload()
        duplicate_skill["project_members"][0]["skills"].append(
            {
                "skill_code": "spring_boot",
                "proficiency_level": 3,
            }
        )
        invalid_allocation = resource_request_payload()
        invalid_allocation["project_members"][0]["allocations"][0][
            "allocation_end_date"
        ] = "2026-08-01"

        for payload in (duplicate_skill, invalid_allocation):
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                PlanningResourceRequest.model_validate(payload)

    def test_request_rejects_duplicate_task_and_member_ids(self):
        duplicate_task = resource_request_payload()
        duplicate_task["wbs_tasks"][1]["wbs_id"] = 3
        duplicate_member = resource_request_payload()
        duplicate_member["project_members"][1]["project_member_id"] = 10

        for payload in (duplicate_task, duplicate_member):
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                PlanningResourceRequest.model_validate(payload)

    def test_member_allows_unknown_capability_without_inventing_role(self):
        member = ProjectMemberCandidate.model_validate(
            {"project_member_id": 1, "roles": [" "], "skills": []}
        )

        self.assertEqual(member.roles, [])
        self.assertEqual(member.skills, [])


if __name__ == "__main__":
    unittest.main()
