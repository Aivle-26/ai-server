import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_schedule.llm_service import (
    ScheduleLLMConfigurationError,
    ScheduleLLMGenerationError,
)
from app.main import app
from tests.fixtures.planning_samples import schedule_request_payload


class FailingGraph:
    def __init__(self, error):
        self.error = error

    def invoke(self, request):
        raise self.error


class PlanningScheduleRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generation_failure_maps_to_502(self):
        with patch(
            "app.domains.planning_schedule.router.planning_schedule_graph",
            FailingGraph(ScheduleLLMGenerationError("schedule failed")),
        ):
            response = self.client.post(
                "/api/v1/planning/schedules/recommend",
                json=schedule_request_payload(),
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "schedule failed")

    def test_configuration_failure_maps_to_503(self):
        with patch(
            "app.domains.planning_schedule.router.planning_schedule_graph",
            FailingGraph(ScheduleLLMConfigurationError("missing key")),
        ):
            response = self.client.post(
                "/api/v1/planning/schedules/recommend",
                json=schedule_request_payload(),
            )
        self.assertEqual(response.status_code, 503)

    def test_invalid_hierarchy_returns_422_before_graph(self):
        payload = schedule_request_payload()
        payload["wbs_items"][2]["parent_wbs_id"] = 1
        with patch(
            "app.domains.planning_schedule.router.planning_schedule_graph",
            FailingGraph(AssertionError("must not run")),
        ):
            response = self.client.post(
                "/api/v1/planning/schedules/recommend", json=payload
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
