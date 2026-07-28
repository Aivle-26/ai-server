import unittest

from pydantic import ValidationError

from app.domains.project_risk.schemas import (
    ArtifactSecurityResponse,
    CandidateMember,
    CurrentAssignee,
    MemberTaskStatus,
    RegisteredArtifact,
    ScheduleWBSItem,
)


class ProjectRiskSchemaTest(unittest.TestCase):
    def test_assignee_workload_and_task_counts_are_bounded(self):
        with self.assertRaises(ValidationError):
            CurrentAssignee(
                member_id=1,
                member_name="Kim",
                workload_rate=101,
            )
        with self.assertRaises(ValidationError):
            CandidateMember(
                member_id=1,
                member_name="Kim",
                role="BACKEND",
                workload_rate=-1,
            )
        with self.assertRaises(ValidationError):
            MemberTaskStatus(
                member_id=1,
                member_name="Kim",
                assigned_task_count=-1,
                completed_task_count=0,
                overdue_task_count=0,
            )

    def test_mutable_skill_defaults_are_not_shared(self):
        first = CurrentAssignee(member_id=1, member_name="Kim")
        second = CurrentAssignee(member_id=2, member_name="Lee")
        first.skills.append("Python")

        self.assertEqual(first.skills, ["Python"])
        self.assertEqual(second.skills, [])

    def test_registered_artifact_defaults_are_stable(self):
        artifact = RegisteredArtifact(
            artifact_name="Requirements",
            artifact_type="DOCUMENT",
        )
        self.assertEqual(artifact.status, "DRAFT")
        self.assertFalse(artifact.approved)
        self.assertIsNone(artifact.version)

    def test_schedule_item_validates_dates_and_progress(self):
        base = {
            "task_id": 1,
            "task_name": "Build API",
            "start_date": "2026-07-20",
            "due_date": "2026-07-25",
        }
        for changes in (
            {"due_date": "2026-07-19"},
            {"progress": -1},
            {"progress": 101},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                ScheduleWBSItem.model_validate({**base, **changes})

    def test_response_rejects_unknown_risk_level(self):
        with self.assertRaises(ValidationError):
            ArtifactSecurityResponse.model_validate(
                {
                    "project_id": 1,
                    "artifact_name": "Report",
                    "security_risk_score": 0,
                    "security_risk_level": "UNKNOWN",
                    "registration_allowed": True,
                    "detections": [],
                    "masked_content": "clean",
                    "recommendations": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
