import os
import unittest
from unittest.mock import patch

from app.domains.planning_schedule.llm_service import (
    PlanningScheduleLLMService,
    ScheduleLLMGenerationError,
)


class PlanningScheduleRegressionTest(unittest.TestCase):
    def test_client_creation_failure_is_mapped_to_generation_error(self):
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "test-key"},
                clear=True,
            ),
            patch(
                "app.domains.planning_schedule.llm_service.OpenAI",
                side_effect=RuntimeError("client failed"),
            ),
        ):
            with self.assertRaises(ScheduleLLMGenerationError):
                PlanningScheduleLLMService().generate(
                    {"tasks": [{"wbs_id": 1}]}
                )


if __name__ == "__main__":
    unittest.main()
