import unittest

from pydantic import ValidationError

from app.domains.planning_wbs.schemas import (
    DEFAULT_METHODOLOGY,
    WBSGenerationRequest,
    WBSGenerationResponse,
)
from tests.fixtures.planning_samples import wbs_request_payload


class PlanningWbsSchemaTest(unittest.TestCase):
    def test_default_methodology_is_copied_and_normalized(self):
        payload = wbs_request_payload()
        payload.pop("methodology")
        first = WBSGenerationRequest.model_validate(payload)
        second = WBSGenerationRequest.model_validate(payload)

        first.methodology.append("Release")
        self.assertEqual(second.methodology, DEFAULT_METHODOLOGY)

    def test_blank_methodology_entries_are_removed(self):
        payload = wbs_request_payload()
        payload["methodology"] = [" Analysis ", " ", "Build"]

        request = WBSGenerationRequest.model_validate(payload)
        self.assertEqual(request.methodology, ["Analysis", "Build"])

    def test_request_accepts_ui_mockup_required_artifact(self):
        payload = wbs_request_payload()
        payload["project_info"]["required_artifacts"].append({
            "artifact_type": "UI_MOCKUP",
            "artifact_name": "핵심 화면 UI 목업",
            "required_version": "1.0",
        })

        request = WBSGenerationRequest.model_validate(payload)

        self.assertEqual(
            request.project_info.required_artifacts[-1].artifact_type,
            "UI_MOCKUP",
        )

    def test_request_rejects_blank_project_empty_requirements_and_duplicates(self):
        cases = []
        blank_project = wbs_request_payload()
        blank_project["project_info"]["project_name"] = " "
        cases.append(blank_project)
        no_requirements = wbs_request_payload()
        no_requirements["requirement_candidates"] = []
        cases.append(no_requirements)
        duplicate_methodology = wbs_request_payload()
        duplicate_methodology["methodology"] = ["Build", "Build"]
        cases.append(duplicate_methodology)

        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                WBSGenerationRequest.model_validate(payload)

    def test_response_rejects_invalid_item_type_and_coverage(self):
        base = {
            "project_name": "AIPM",
            "methodology": ["Build"],
            "wbs_items": [
                {
                    "wbs_id": 1,
                    "wbs_code": "1",
                    "level": 1,
                    "sort_order": 1,
                    "item_type": "PHASE",
                    "wbs_name": "Build",
                    "description": "Build",
                }
            ],
            "requirement_coverage": {
                "total_requirements": 1,
                "mapped_requirements": 1,
                "coverage_rate": 100,
            },
            "artifact_coverage": {
                "total_required_artifacts": 0,
                "mapped_artifacts": 0,
                "coverage_rate": 100,
            },
            "generation_status": "SUCCEEDED",
        }
        for changes in (
            {
                "wbs_items": [
                    {**base["wbs_items"][0], "item_type": "MILESTONE"}
                ]
            },
            {
                "requirement_coverage": {
                    **base["requirement_coverage"],
                    "coverage_rate": 101,
                }
            },
            {"generation_status": "FAILED"},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                ValidationError
            ):
                WBSGenerationResponse.model_validate({**base, **changes})


if __name__ == "__main__":
    unittest.main()
