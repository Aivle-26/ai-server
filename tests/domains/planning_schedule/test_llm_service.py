import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.domains.planning_schedule.llm_service import (
    GeneratedSchedulePlan,
    PlanningScheduleLLMService,
    ScheduleLLMConfigurationError,
    ScheduleLLMGenerationError,
)


class PlanningScheduleLlmServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningScheduleLLMService()

    def test_missing_key_does_not_construct_client(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "app.domains.planning_schedule.llm_service.OpenAI"
            ) as client,
        ):
            with self.assertRaises(ScheduleLLMConfigurationError):
                self.service.generate({"tasks": []})
        client.assert_not_called()

    def test_api_timeout_is_mapped_to_generation_error(self):
        responses = MagicMock()
        responses.parse.side_effect = TimeoutError("timeout")
        client = SimpleNamespace(responses=responses)
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_schedule.llm_service.OpenAI",
                return_value=client,
            ),
        ):
            with self.assertRaisesRegex(
                ScheduleLLMGenerationError, "기간을 추정"
            ):
                self.service.generate({"tasks": [{"wbs_id": 1}]})

    def test_none_output_is_rejected_and_store_is_false(self):
        responses = MagicMock()
        responses.parse.return_value = SimpleNamespace(output_parsed=None)
        client = SimpleNamespace(responses=responses)
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_schedule.llm_service.OpenAI",
                return_value=client,
            ),
        ):
            with self.assertRaisesRegex(
                ScheduleLLMGenerationError, "구조화된 일정"
            ):
                self.service.generate({"tasks": [{"wbs_id": 1}]})

        request = responses.parse.call_args.kwargs
        self.assertFalse(request["store"])
        self.assertIs(request["text_format"], GeneratedSchedulePlan)


if __name__ == "__main__":
    unittest.main()
