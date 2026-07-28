import unittest

from pydantic import ValidationError

from app.domains.planning_documents.schemas import (
    PlanningDocumentExtractionResponse,
    ProjectBasicInfo,
    RequiredArtifact,
    RequirementCandidate,
)


class PlanningDocumentSchemaTest(unittest.TestCase):
    def test_project_info_uses_independent_list_defaults(self):
        first = ProjectBasicInfo()
        second = ProjectBasicInfo()
        first.key_features.append("feature")

        self.assertEqual(first.key_features, ["feature"])
        self.assertEqual(second.key_features, [])

    def test_required_artifact_defaults_to_version_one(self):
        artifact = RequiredArtifact(
            artifact_type="ERD", artifact_name="Database diagram"
        )
        self.assertEqual(artifact.required_version, "1.0")

    def test_requirement_rejects_invalid_id_enum_and_date(self):
        base = {
            "requirement_id": 1,
            "function_name": "Login",
            "requirement_text": "Users can log in.",
            "source_document": "rfp.txt",
        }
        for changes in (
            {"requirement_id": 0},
            {"category": "UNKNOWN"},
            {"priority": "CRITICAL"},
            {"due_date": "not-a-date"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                RequirementCandidate.model_validate({**base, **changes})

    def test_response_serializes_nested_dates_and_defaults(self):
        response = PlanningDocumentExtractionResponse.model_validate(
            {
                "project_info": {
                    "project_name": "AIPM",
                    "period_start": "2026-08-03",
                },
                "requirement_candidates": [
                    {
                        "requirement_id": 1,
                        "function_name": "Login",
                        "requirement_text": "Users can log in.",
                        "source_document": "rfp.txt",
                    }
                ],
                "documents": [
                    {
                        "file_name": "rfp.txt",
                        "file_type": "TXT",
                        "character_count": 17,
                        "processing_mode": "TEXT",
                    }
                ],
                "llm_status": "SKIPPED_NO_API_KEY",
            }
        )
        dumped = response.model_dump(mode="json")

        self.assertEqual(dumped["project_info"]["period_start"], "2026-08-03")
        self.assertEqual(
            dumped["requirement_candidates"][0]["priority"], "UNSPECIFIED"
        )


if __name__ == "__main__":
    unittest.main()
