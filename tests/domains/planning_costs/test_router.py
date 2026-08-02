import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_costs.llm_service import (
    CostLLMConfigurationError,
    CostLLMGenerationError,
)
from app.main import app
from tests.fixtures.planning_samples import cost_request_payload


class FailingGraph:
    def __init__(self, error):
        self.error = error

    def invoke(self, request):
        raise self.error


class PlanningCostRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generation_failure_maps_to_502(self):
        with patch(
            "app.domains.planning_costs.router.planning_cost_graph",
            FailingGraph(CostLLMGenerationError("cost failed")),
        ):
            response = self.client.post(
                "/api/v1/planning/costs/estimate",
                json=cost_request_payload(),
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["message"], "cost failed")

    def test_configuration_failure_maps_to_503(self):
        with patch(
            "app.domains.planning_costs.router.planning_cost_graph",
            FailingGraph(CostLLMConfigurationError("missing key")),
        ):
            response = self.client.post(
                "/api/v1/planning/costs/estimate",
                json=cost_request_payload(),
            )
        self.assertEqual(response.status_code, 503)

    def test_invalid_scale_returns_422_before_graph(self):
        payload = cost_request_payload()
        payload["service_scale"] = "INVALID"
        with patch(
            "app.domains.planning_costs.router.planning_cost_graph",
            FailingGraph(AssertionError("must not run")),
        ):
            response = self.client.post(
                "/api/v1/planning/costs/estimate", json=payload
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
