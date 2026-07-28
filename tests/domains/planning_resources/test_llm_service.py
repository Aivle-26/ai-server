import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.domains.planning_resources.llm_service import (
    GeneratedResourcePlan,
    PlanningResourceLLMService,
    ResourceLLMConfigurationError,
    ResourceLLMGenerationError,
)


class PlanningResourceLlmServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningResourceLLMService()

    def test_missing_key_fails_without_client(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "app.domains.planning_resources.llm_service.OpenAI"
            ) as client,
        ):
            with self.assertRaises(ResourceLLMConfigurationError):
                self.service.generate([{"tasks": []}])
        client.assert_not_called()

    def test_client_creation_failure_is_wrapped(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_resources.llm_service.OpenAI",
                side_effect=RuntimeError("bad client"),
            ),
        ):
            with self.assertRaisesRegex(
                ResourceLLMGenerationError, "인력·공수 추정 요청"
            ):
                self.service.generate([{"tasks": [{"wbs_id": 1}]}])

    def test_none_output_and_timeout_are_generation_errors(self):
        for response_or_error in (None, TimeoutError("timeout")):
            responses = MagicMock()
            if isinstance(response_or_error, Exception):
                responses.parse.side_effect = response_or_error
            else:
                responses.parse.return_value = SimpleNamespace(
                    output_parsed=None
                )
            with self.subTest(value=response_or_error):
                with self.assertRaises(ResourceLLMGenerationError):
                    self.service._request_one(
                        SimpleNamespace(responses=responses),
                        {"tasks": []},
                    )
                self.assertFalse(
                    responses.parse.call_args.kwargs["store"]
                )
                self.assertIs(
                    responses.parse.call_args.kwargs["text_format"],
                    GeneratedResourcePlan,
                )

    def test_instructions_constrain_role_skill_and_forbid_assignment(self):
        instructions = self.service._instructions()
        for phrase in (
            "allowed_role_codes",
            "allowed_skill_codes",
            "담당자 ID",
            "MM",
        ):
            self.assertIn(phrase, instructions)


if __name__ == "__main__":
    unittest.main()
