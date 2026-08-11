import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.domains.planning_wbs.llm_service import (
    GeneratedWBSPhase,
    GeneratedWBSPlan,
    PlanningWBSLLMService,
    WBSLLMConfigurationError,
    WBSLLMGenerationError,
)


def plan():
    return GeneratedWBSPlan(
        phases=[
            GeneratedWBSPhase(
                phase_name="Build",
                description="Build",
                completion_criteria=["Complete"],
                work_packages=[],
            )
        ]
    )


class Responses:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(output_parsed=self.result)


class PlanningWbsLlmServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = PlanningWBSLLMService()

    def test_missing_key_fails_before_openai(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "app.domains.planning_wbs.llm_service.OpenAI"
            ) as client,
        ):
            with self.assertRaises(WBSLLMConfigurationError):
                self.service.generate([{"requirements": []}])
        client.assert_not_called()

    def test_none_structured_output_is_generation_error(self):
        responses = Responses(result=None)
        with self.assertRaisesRegex(
            WBSLLMGenerationError, "구조화된 WBS"
        ):
            self.service._request_one(
                SimpleNamespace(responses=responses),
                {"requirements": []},
            )
        self.assertFalse(responses.request["store"])

    def test_api_timeout_is_mapped_to_generation_error(self):
        responses = Responses(error=TimeoutError("timeout"))
        with self.assertRaisesRegex(
            WBSLLMGenerationError, "WBS 구조"
        ):
            self.service._request_one(
                SimpleNamespace(responses=responses),
                {"requirements": []},
            )

    def test_client_creation_failure_is_mapped_by_generate(self):
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True),
            patch(
                "app.domains.planning_wbs.llm_service.OpenAI",
                side_effect=RuntimeError("bad client"),
            ),
        ):
            with self.assertRaisesRegex(
                WBSLLMGenerationError, "OpenAI WBS 생성 요청"
            ):
                self.service.generate([{"requirements": []}])

    def test_client_uses_five_minute_timeout(self):
        responses = Responses(result=plan())
        with patch(
            "app.domains.planning_wbs.llm_service.OpenAI",
            return_value=SimpleNamespace(responses=responses),
        ) as client:
            result = self.service._generate_one(
                "test-key",
                {"requirements": []},
            )

        self.assertIsInstance(result, GeneratedWBSPlan)
        client.assert_called_once_with(
            api_key="test-key",
            timeout=300,
            max_retries=1,
        )

    def test_instructions_forbid_schedule_and_assignee_fields(self):
        instructions = self.service._instructions()
        for phrase in ("일정", "담당자", "requirement_id", "phase_name"):
            self.assertIn(phrase, instructions)


if __name__ == "__main__":
    unittest.main()
