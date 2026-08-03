import json
import unittest
from datetime import date

from pydantic import ValidationError

from app.domains.planning_resources.capability_and_view_models import (
    AdapterResult,
    AssessmentStatus,
    Evidence,
    MemberCapabilityProfile,
    RoleAssessment,
    SkillAssessment,
    to_project_member_candidate,
)
from app.domains.planning_resources.schemas import (
    MemberAllocation,
    ProjectMemberCandidate,
)


def evidence_payload() -> dict[str, str]:
    return {
        "source_type": " GITHUB ",
        "source_reference": " org/repository ",
        "description": " implemented the feature ",
    }


def role(
    status: AssessmentStatus | str = AssessmentStatus.DECLARED,
    confidence: float = 0.9,
    role_code: str = "BACKEND",
) -> RoleAssessment:
    evidences = (
        [Evidence.model_validate(evidence_payload())]
        if status == AssessmentStatus.INFERRED or status == "INFERRED"
        else []
    )
    return RoleAssessment(
        role_code=role_code,
        confidence=confidence,
        evidences=evidences,
        status=status,
    )


def skill(
    status: AssessmentStatus | str,
    proficiency_level: int,
    confidence: float,
    skill_code: str = "PYTHON",
) -> SkillAssessment:
    evidences = (
        [Evidence.model_validate(evidence_payload())]
        if status == AssessmentStatus.INFERRED or status == "INFERRED"
        else []
    )
    return SkillAssessment(
        skill_code=skill_code,
        proficiency_level=proficiency_level,
        experience_months=20,
        confidence=confidence,
        evidences=evidences,
        status=status,
    )


class CapabilityModelTest(unittest.TestCase):
    def test_assessment_status_is_string_enum_and_json_is_string(self):
        assessment = role(status=AssessmentStatus.CONFIRMED)

        self.assertIsInstance(AssessmentStatus.CONFIRMED, str)
        self.assertEqual(str(AssessmentStatus.CONFIRMED), "CONFIRMED")
        self.assertIsInstance(assessment.status, AssessmentStatus)
        self.assertEqual(
            json.loads(assessment.model_dump_json())["status"],
            "CONFIRMED",
        )

    def test_code_fields_are_trimmed_normalized_and_reject_blanks(self):
        normalized_role = role(role_code=" backend ")
        normalized_skill = skill(
            "DECLARED",
            3,
            0.8,
            skill_code=" python ",
        )

        self.assertEqual(normalized_role.role_code, "BACKEND")
        self.assertEqual(normalized_skill.skill_code, "PYTHON")
        for invalid_value in ("", "   "):
            with self.subTest(
                model="skill",
                invalid_value=invalid_value,
            ), self.assertRaises(ValidationError):
                skill("DECLARED", 3, 0.8, skill_code=invalid_value)
            with self.subTest(
                model="role",
                invalid_value=invalid_value,
            ), self.assertRaises(ValidationError):
                role(role_code=invalid_value)

    def test_evidence_trims_text_and_rejects_blank_values(self):
        evidence = Evidence.model_validate(evidence_payload())

        self.assertEqual(evidence.source_type, "GITHUB")
        self.assertEqual(evidence.source_reference, "org/repository")
        self.assertEqual(evidence.description, "implemented the feature")

        for field_name in ("source_type", "source_reference", "description"):
            for invalid_value in ("", "   "):
                payload = evidence_payload()
                payload[field_name] = invalid_value
                with self.subTest(
                    field_name=field_name,
                    invalid_value=invalid_value,
                ), self.assertRaises(ValidationError):
                    Evidence.model_validate(payload)

    def test_inferred_assessments_require_evidence(self):
        with self.assertRaises(ValidationError):
            RoleAssessment(
                role_code="BACKEND",
                confidence=0.8,
                status=AssessmentStatus.INFERRED,
            )
        with self.assertRaises(ValidationError):
            SkillAssessment(
                skill_code="PYTHON",
                proficiency_level=3,
                confidence=0.8,
                status=AssessmentStatus.INFERRED,
            )

    def test_code_fields_reject_non_strings_with_validation_error(self):
        for invalid_value in (None, 123):
            with self.subTest(
                model="skill",
                invalid_value=invalid_value,
            ), self.assertRaises(ValidationError):
                SkillAssessment.model_validate(
                    {
                        "skill_code": invalid_value,
                        "proficiency_level": 3,
                        "confidence": 0.8,
                        "status": "DECLARED",
                    }
                )
            with self.subTest(
                model="role",
                invalid_value=invalid_value,
            ), self.assertRaises(ValidationError):
                RoleAssessment.model_validate(
                    {
                        "role_code": invalid_value,
                        "confidence": 0.8,
                        "status": "DECLARED",
                    }
                )

    def test_profile_allows_different_statuses_in_the_same_area(self):
        profile = MemberCapabilityProfile(
            project_member_id=7,
            primary_roles=[
                role(status="DECLARED"),
                role(status="CONFIRMED"),
            ],
            skills=[
                skill("DECLARED", 5, 0.9),
                skill("CONFIRMED", 2, 0.6),
            ],
            profile_confidence=0.9,
        )

        self.assertEqual(len(profile.primary_roles), 2)
        self.assertEqual(len(profile.skills), 2)

    def test_profile_rejects_duplicate_role_and_skill_status_pairs(self):
        with self.assertRaises(ValidationError):
            MemberCapabilityProfile(
                project_member_id=7,
                primary_roles=[role(), role()],
                profile_confidence=0.9,
            )
        with self.assertRaises(ValidationError):
            MemberCapabilityProfile(
                project_member_id=7,
                primary_roles=[role()],
                skills=[
                    skill("DECLARED", 3, 0.8),
                    skill("DECLARED", 4, 0.9),
                ],
                profile_confidence=0.9,
            )

    def test_profile_rejects_role_code_across_primary_and_secondary(self):
        with self.assertRaises(ValidationError):
            MemberCapabilityProfile(
                project_member_id=7,
                primary_roles=[role(status="DECLARED")],
                secondary_roles=[role(status="CONFIRMED")],
                profile_confidence=0.9,
            )


class CapabilityAdapterTest(unittest.TestCase):
    def test_confirmed_assessment_wins_and_metadata_preserves_selection(self):
        allocations = [
            MemberAllocation(
                allocation_start_date=date(2026, 8, 10),
                allocation_end_date=date(2026, 8, 24),
                available_hours_per_week=32.0,
                allocation_status="ACTIVE",
            )
        ]
        allocations_before = [item.model_dump() for item in allocations]
        profile = MemberCapabilityProfile(
            project_member_id=17,
            primary_roles=[role(status="DECLARED", confidence=0.9)],
            skills=[
                skill("INFERRED", 4, 0.95),
                skill("CONFIRMED", 2, 0.2),
                skill("DECLARED", 5, 0.99),
                skill("DECLARED", 3, 0.6, skill_code="JAVA"),
            ],
            profile_confidence=0.9,
        )

        result = to_project_member_candidate(profile, allocations)

        self.assertTrue(result.eligible)
        self.assertIsInstance(result, AdapterResult)
        self.assertIsInstance(result.candidate, ProjectMemberCandidate)
        self.assertEqual(result.candidate.project_member_id, 17)
        self.assertEqual(
            [item.skill_code for item in result.candidate.skills],
            ["PYTHON"],
        )
        self.assertEqual(result.candidate.skills[0].proficiency_level, 2)
        self.assertEqual(result.candidate.allocations, allocations)
        self.assertEqual(
            [item.model_dump() for item in allocations],
            allocations_before,
        )

        selected = result.selected_skill_assessments
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].skill_code, "PYTHON")
        self.assertEqual(selected[0].status, AssessmentStatus.CONFIRMED)
        self.assertEqual(selected[0].confidence, 0.2)
        self.assertEqual(selected[0].proficiency_level, 2)
        self.assertEqual(
            result.selected_role_assessments[0].status,
            AssessmentStatus.DECLARED,
        )
        self.assertEqual(
            result.selected_role_assessments[0].role_code,
            "BACKEND",
        )

        python_exclusions = [
            item for item in result.excluded_skills if item.code == "PYTHON"
        ]
        self.assertEqual(len(python_exclusions), 2)
        self.assertEqual(
            {item.status for item in python_exclusions},
            {AssessmentStatus.DECLARED, AssessmentStatus.INFERRED},
        )
        self.assertTrue(
            all(item.proficiency_level in {4, 5} for item in python_exclusions)
        )
        self.assertTrue(all(item.reason for item in python_exclusions))

        java_exclusion = next(
            item for item in result.excluded_skills if item.code == "JAVA"
        )
        self.assertEqual(java_exclusion.status, AssessmentStatus.DECLARED)
        self.assertEqual(java_exclusion.confidence, 0.6)
        self.assertEqual(java_exclusion.proficiency_level, 3)
        self.assertEqual(
            java_exclusion.reason,
            "Confidence below threshold",
        )
        dumped = json.loads(result.model_dump_json())
        self.assertEqual(
            dumped["selected_skill_assessments"][0]["status"],
            "CONFIRMED",
        )

    def test_adapter_rejects_profile_without_an_eligible_role(self):
        profile = MemberCapabilityProfile(
            project_member_id=17,
            primary_roles=[role(confidence=0.6)],
            profile_confidence=0.9,
        )

        result = to_project_member_candidate(profile, [])

        self.assertFalse(result.eligible)
        self.assertIsNone(result.candidate)
        self.assertEqual(result.rejection_reasons, ["No eligible roles found."])
        self.assertEqual(result.excluded_roles[0].code, "BACKEND")


if __name__ == "__main__":
    unittest.main()
