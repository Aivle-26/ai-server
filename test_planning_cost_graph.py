import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.planning_cost_graph import PlanningCostGraph
from app.main import app
from app.schemas.planning_cost import PlanningCostRequest
from app.services.planning_cost_llm_service import (
    CostLLMConfigurationError,
    GeneratedCostAnalysis,
    GeneratedPotentialCost,
    PlanningCostLLMService,
)


def sample_request(**overrides) -> PlanningCostRequest:
    payload = {
        "project_id": 1,
        "project_name": "AI 학생 맞춤형 학습지원시스템 구축",
        "wbs_efforts": [
            {
                "wbs_id": 101,
                "wbs_name": "학습 현황 대시보드 개발",
                "description": "학생별 학습 현황 조회 기능을 개발한다.",
                "estimated_mm": 2.0,
            },
            {
                "wbs_id": 102,
                "wbs_name": "AI 학습 분석 기능 개발",
                "description": "학습 데이터를 AI로 분석한다.",
                "estimated_mm": 2.35,
            },
        ],
        "average_monthly_unit_price": 8_000_000,
        "operation_months": 6,
        "service_scale": "SMALL",
        "uses_ai_api": True,
        "paid_license_user_count": 5,
        "include_vat": True,
    }
    payload.update(overrides)
    return PlanningCostRequest.model_validate(payload)


def generated_analysis() -> GeneratedCostAnalysis:
    return GeneratedCostAnalysis(potential_additional_costs=[
        GeneratedPotentialCost(
            cost_type="MONITORING",
            cost_name="운영 모니터링 서비스",
            reason="서비스 운영 중 장애와 성능을 확인할 필요가 있습니다.",
        )
    ])


class FakeCostLLMService:
    def generate(self, context):
        return generated_analysis()


class SuccessfulCostGraph:
    def invoke(self, request):
        return PlanningCostGraph(
            llm_service=FakeCostLLMService(),
        ).invoke(request)


class MissingKeyCostGraph:
    def invoke(self, request):
        raise CostLLMConfigurationError(
            "OPENAI_API_KEY가 설정되지 않았습니다."
        )


class CapturingResponses:
    def __init__(self):
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=generated_analysis())


class PlanningCostGraphTest(unittest.TestCase):
    def build_graph(self):
        return PlanningCostGraph(llm_service=FakeCostLLMService())

    def test_graph_reuses_wbs_mm_and_calculates_single_estimate(self):
        result = self.build_graph().invoke(sample_request())

        self.assertEqual(result["project_id"], 1)
        self.assertEqual(result["total_estimated_mm"], 4.35)

        summary = result["cost_summary"]
        self.assertEqual(summary["labor_cost"], 34_800_000)
        self.assertEqual(summary["server_cost"], 1_800_000)
        self.assertEqual(summary["license_cost"], 1_200_000)
        self.assertEqual(summary["ai_api_cost"], 900_000)
        self.assertEqual(summary["base_cost"], 38_700_000)

        estimate = result["estimate"]
        self.assertEqual(estimate["contingency_rate"], 10)
        self.assertEqual(estimate["contingency_amount"], 3_870_000)
        self.assertEqual(estimate["supply_amount"], 42_570_000)
        self.assertEqual(estimate["vat"], 4_257_000)
        self.assertEqual(estimate["total_amount"], 46_827_000)
        self.assertEqual(
            result["unpriced_items"],
            ["운영 모니터링 서비스"],
        )

    def test_optional_costs_and_vat_can_be_excluded(self):
        result = self.build_graph().invoke(sample_request(
            uses_ai_api=False,
            paid_license_user_count=0,
            include_vat=False,
        ))

        summary = result["cost_summary"]
        self.assertEqual(summary["license_cost"], 0)
        self.assertEqual(summary["ai_api_cost"], 0)
        self.assertEqual(summary["base_cost"], 36_600_000)

        estimate = result["estimate"]
        self.assertEqual(estimate["contingency_amount"], 3_660_000)
        self.assertEqual(estimate["supply_amount"], 40_260_000)
        self.assertEqual(estimate["vat"], 0)
        self.assertEqual(estimate["total_amount"], 40_260_000)

    def test_request_rejects_duplicate_wbs_ids(self):
        payload = sample_request().model_dump(mode="json")
        payload["wbs_efforts"].append(payload["wbs_efforts"][0])

        with self.assertRaises(ValidationError):
            PlanningCostRequest.model_validate(payload)

    def test_llm_only_receives_compact_wbs_context(self):
        request = sample_request()
        context = self.build_graph().cost_service.prepare_context(request)

        self.assertEqual(len(context["wbs_items"]), 2)
        self.assertNotIn("average_monthly_unit_price", context)
        self.assertNotIn("operation_months", context)
        self.assertEqual(
            context["already_priced_cost_types"],
            ["LABOR", "SERVER", "LICENSE", "AI_API"],
        )

    def test_openai_request_uses_structured_output_without_storage(self):
        responses = CapturingResponses()
        fake_client = SimpleNamespace(responses=responses)
        service = PlanningCostLLMService()

        result = service._request(fake_client, {"wbs_items": []})

        self.assertIsInstance(result, GeneratedCostAnalysis)
        self.assertIs(
            responses.request["text_format"],
            GeneratedCostAnalysis,
        )
        self.assertFalse(responses.request["store"])

    def test_fastapi_returns_cost_estimate(self):
        payload = sample_request().model_dump(mode="json")
        with patch.object(
            importlib.import_module("app.main"),
            "planning_cost_graph",
            SuccessfulCostGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/costs/estimate",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project_id"], 1)
        self.assertEqual(response.json()["total_estimated_mm"], 4.35)
        self.assertNotIn("estimate_versions", response.json())
        self.assertIn("estimate", response.json())

    def test_fastapi_returns_503_when_api_key_is_missing(self):
        payload = sample_request().model_dump(mode="json")
        with patch.object(
            importlib.import_module("app.main"),
            "planning_cost_graph",
            MissingKeyCostGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/costs/estimate",
                json=payload,
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_openapi_describes_cost_endpoint_in_korean(self):
        operation = app.openapi()["paths"][
            "/api/v1/planning/costs/estimate"
        ]["post"]

        self.assertEqual(operation["summary"], "프로젝트 예상 견적 생성")
        self.assertIn("WBS별 MM", operation["description"])
        self.assertIn("단일 권장 견적", operation["description"])
        schemas = app.openapi()["components"]["schemas"]
        self.assertEqual(
            schemas["PlanningCostRequest"]["properties"]["project_id"]["type"],
            "integer",
        )
        self.assertEqual(
            schemas["CostWBSEffort"]["properties"]["wbs_id"]["type"],
            "integer",
        )


if __name__ == "__main__":
    unittest.main()
