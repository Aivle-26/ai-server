import unittest

from app.domains.planning_costs.llm_service import (
    GeneratedCostAnalysis,
    GeneratedPotentialCost,
)
from app.domains.planning_costs.schemas import PlanningCostRequest
from app.domains.planning_costs.service import PlanningCostService
from tests.fixtures.planning_samples import cost_request_payload


class PlanningCostServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningCostService()

    def test_won_amounts_use_half_up_rounding(self):
        payload = cost_request_payload()
        payload.update(
            {
                "average_monthly_unit_price": 1,
                "operation_months": 1,
                "uses_ai_api": False,
                "paid_license_user_count": 0,
                "include_vat": False,
            }
        )
        payload["wbs_efforts"] = [
            {
                "wbs_id": 1,
                "wbs_name": "Tiny",
                "description": "Rounding check",
                "estimated_mm": 1.5,
            }
        ]
        request = PlanningCostRequest.model_validate(payload)

        result = self.service.calculate(
            request, GeneratedCostAnalysis()
        )
        self.assertEqual(result["cost_summary"]["labor_cost"], 2)

    def test_additional_cost_names_are_case_insensitively_deduplicated(self):
        analysis = GeneratedCostAnalysis(
            potential_additional_costs=[
                GeneratedPotentialCost(
                    cost_type="MONITORING",
                    cost_name="Observability",
                    reason="Metrics are required",
                ),
                GeneratedPotentialCost(
                    cost_type="MONITORING",
                    cost_name="observability",
                    reason="Duplicate name",
                ),
            ]
        )
        request = PlanningCostRequest.model_validate(cost_request_payload())

        result = self.service.calculate(request, analysis)
        self.assertEqual(result["unpriced_items"], ["Observability"])

    def test_service_scale_changes_server_and_ai_costs(self):
        totals = {}
        for scale in ("SMALL", "MEDIUM", "LARGE"):
            payload = cost_request_payload()
            payload["service_scale"] = scale
            result = self.service.calculate(
                PlanningCostRequest.model_validate(payload),
                GeneratedCostAnalysis(),
            )
            totals[scale] = (
                result["cost_summary"]["server_cost"],
                result["cost_summary"]["ai_api_cost"],
            )

        self.assertLess(totals["SMALL"][0], totals["MEDIUM"][0])
        self.assertLess(totals["MEDIUM"][0], totals["LARGE"][0])
        self.assertLess(totals["SMALL"][1], totals["LARGE"][1])

    def test_calculation_does_not_mutate_request(self):
        request = PlanningCostRequest.model_validate(cost_request_payload())
        before = request.model_dump(mode="json")
        self.service.calculate(request, GeneratedCostAnalysis())
        self.assertEqual(request.model_dump(mode="json"), before)


if __name__ == "__main__":
    unittest.main()
