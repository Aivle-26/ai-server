import unittest

from pydantic import ValidationError

from app.domains.planning_costs.schemas import PlanningCostRequest
from tests.fixtures.planning_samples import cost_request_payload


class PlanningCostSchemaTest(unittest.TestCase):
    def test_request_strips_project_and_wbs_text(self):
        payload = cost_request_payload()
        payload["project_name"] = " AIPM "
        payload["wbs_efforts"][0]["wbs_name"] = " Review "

        request = PlanningCostRequest.model_validate(payload)
        self.assertEqual(request.project_name, "AIPM")
        self.assertEqual(request.wbs_efforts[0].wbs_name, "Review")

    def test_request_rejects_blank_text_duplicate_ids_and_unknown_scale(self):
        cases = []
        blank = cost_request_payload()
        blank["wbs_efforts"][0]["description"] = " "
        cases.append(blank)
        duplicate = cost_request_payload()
        duplicate["wbs_efforts"][1]["wbs_id"] = 3
        cases.append(duplicate)
        scale = cost_request_payload()
        scale["service_scale"] = "XLARGE"
        cases.append(scale)

        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                PlanningCostRequest.model_validate(payload)

    def test_numeric_bounds_are_enforced(self):
        changes = (
            ("average_monthly_unit_price", 0),
            ("operation_months", 0),
            ("operation_months", 121),
            ("paid_license_user_count", -1),
        )
        for field, value in changes:
            payload = cost_request_payload()
            payload[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                ValidationError
            ):
                PlanningCostRequest.model_validate(payload)

    def test_boolean_defaults_are_stable(self):
        payload = cost_request_payload()
        payload.pop("uses_ai_api")
        payload.pop("include_vat")
        payload.pop("paid_license_user_count")

        request = PlanningCostRequest.model_validate(payload)
        self.assertFalse(request.uses_ai_api)
        self.assertTrue(request.include_vat)
        self.assertEqual(request.paid_license_user_count, 0)


if __name__ == "__main__":
    unittest.main()
