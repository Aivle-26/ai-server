import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_resources.llm_service import (
    ResourceLLMConfigurationError,
    ResourceLLMGenerationError,
)
from app.main import app
from tests.fixtures.planning_samples import resource_request_payload


class FailingGraph:
    def __init__(self, error):
        self.error = error

    def invoke(self, request):
        raise self.error


class PlanningResourceRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generation_failure_maps_to_502(self):
        with patch(
            "app.domains.planning_resources.router.planning_resource_graph",
            FailingGraph(ResourceLLMGenerationError("resource failed")),
        ):
            response = self.client.post(
                "/api/v1/planning/resources/recommend",
                json=resource_request_payload(),
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "resource failed")

    def test_configuration_failure_maps_to_503(self):
        with patch(
            "app.domains.planning_resources.router.planning_resource_graph",
            FailingGraph(ResourceLLMConfigurationError("missing key")),
        ):
            response = self.client.post(
                "/api/v1/planning/resources/recommend",
                json=resource_request_payload(),
            )
        self.assertEqual(response.status_code, 503)

    def test_invalid_date_returns_422_before_graph(self):
        payload = resource_request_payload()
        payload["wbs_tasks"][0]["end_date"] = "2026-08-01"
        with patch(
            "app.domains.planning_resources.router.planning_resource_graph",
            FailingGraph(AssertionError("must not run")),
        ):
            response = self.client.post(
                "/api/v1/planning/resources/recommend", json=payload
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
