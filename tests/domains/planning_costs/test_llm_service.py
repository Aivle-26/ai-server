import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.domains.planning_costs.llm_service import (
    CostLLMConfigurationError,
    CostLLMGenerationError,
    GeneratedCostAnalysis,
    PlanningCostLLMService,
)


class PlanningCostLlmServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningCostLLMService()

    def test_missing_key_does_not_construct_client(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "app.domains.planning_costs.llm_service.OpenAI"
            ) as client,
        ):
            with self.assertRaises(CostLLMConfigurationError):
                self.service.generate({"wbs_items": []})
        client.assert_not_called()

    def test_client_creation_failure_is_wrapped(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_costs.llm_service.OpenAI",
                side_effect=RuntimeError("bad client"),
            ),
        ):
            with self.assertRaisesRegex(
                CostLLMGenerationError, "분석 요청"
            ):
                self.service.generate({"wbs_items": []})

    def test_api_error_and_none_output_are_generation_errors(self):
        for output, error in (
            (None, None),
            (None, TimeoutError("timeout")),
        ):
            responses = MagicMock()
            if error:
                responses.parse.side_effect = error
            else:
                responses.parse.return_value = SimpleNamespace(
                    output_parsed=output
                )
            with self.subTest(error=error):
                with self.assertRaises(CostLLMGenerationError):
                    self.service._request(
                        SimpleNamespace(responses=responses),
                        {"wbs_items": []},
                    )
                request = responses.parse.call_args.kwargs
                self.assertFalse(request["store"])
                self.assertIs(
                    request["text_format"], GeneratedCostAnalysis
                )

    def test_prompt_forbids_amount_generation_and_requires_evidence(self):
        instructions = self.service._instructions()
        self.assertIn("금액, 단가, 수량을 추정하거나 생성하지 마세요", instructions)
        self.assertIn("WBS에서 합리적으로 근거", instructions)
        self.assertIn("빈 목록", instructions)


if __name__ == "__main__":
    unittest.main()
