import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_wbs.llm_service import (
    WBSLLMConfigurationError,
    WBSLLMGenerationError,
)
from app.main import app
from tests.fixtures.planning_samples import wbs_request_payload


class FailingGraph:
    def __init__(self, error):
        self.error = error

    def invoke(self, request):
        raise self.error


class PlanningWbsRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generation_failure_maps_to_502(self):
        graph = FailingGraph(WBSLLMGenerationError("generation failed"))
        with patch(
            "app.domains.planning_wbs.router.planning_wbs_graph", graph
        ):
            response = self.client.post(
                "/api/v1/planning/wbs/generate",
                json=wbs_request_payload(),
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "generation failed")

    def test_configuration_failure_maps_to_503(self):
        graph = FailingGraph(WBSLLMConfigurationError("missing key"))
        with patch(
            "app.domains.planning_wbs.router.planning_wbs_graph", graph
        ):
            response = self.client.post(
                "/api/v1/planning/wbs/generate",
                json=wbs_request_payload(),
            )

        self.assertEqual(response.status_code, 503)

    def test_validation_failure_does_not_invoke_graph(self):
        graph = FailingGraph(AssertionError("must not run"))
        payload = wbs_request_payload()
        payload["requirement_candidates"] = []
        with patch(
            "app.domains.planning_wbs.router.planning_wbs_graph", graph
        ):
            response = self.client.post(
                "/api/v1/planning/wbs/generate", json=payload
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
