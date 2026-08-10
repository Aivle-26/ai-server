import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domains.planning_costs.effort_graph import PlanningEffortGraph
from app.domains.planning_costs.effort_llm_service import (
    EffortLLMConfigurationError,
    GeneratedEffortPlan,
    GeneratedOverlapCandidate,
    GeneratedWBSEffort,
    PlanningEffortLLMService,
)
from app.domains.planning_costs.effort_schemas import (
    DETAILED_JOB_CATEGORY,
    KosaDetailedJob,
    KosaJobCategory,
    PlanningEffortEstimateRequest,
)
from app.domains.planning_costs.effort_service import (
    InvalidEffortLLMResponseError,
    PlanningEffortService,
)
from app.main import app


def request_payload() -> dict:
    return {
        "project_id": 7,
        "project_name": "입찰 프로젝트 관리 시스템",
        "wbs_tasks": [
            {
                "wbs_id": 101,
                "wbs_name": "요구사항 분석",
                "description": "사용자 요구사항과 업무 절차를 분석한다.",
                "parent_wbs_id": 10,
                "level": 3,
                "item_type": "TASK",
                "work_package_id": 10,
                "work_package_name": "요구사항 정의",
                "start_date": "2026-09-01",
                "end_date": "2026-09-10",
            },
            {
                "wbs_id": 102,
                "wbs_name": "백엔드 API 개발",
                "description": "프로젝트 관리 REST API를 구현한다.",
                "parent_wbs_id": 20,
                "level": 3,
                "item_type": "TASK",
                "work_package_id": 20,
                "work_package_name": "서비스 개발",
                "start_date": "2026-09-11",
                "end_date": "2026-10-20",
            },
            {
                "wbs_id": 103,
                "wbs_name": "연동 API 개발",
                "description": "외부 시스템 연동 API를 구현한다.",
                "parent_wbs_id": 20,
                "level": 3,
                "item_type": "TASK",
                "work_package_id": 20,
                "work_package_name": "서비스 개발",
                "start_date": "2026-10-01",
                "end_date": "2026-10-20",
            },
        ],
    }


def generated_plan() -> GeneratedEffortPlan:
    return GeneratedEffortPlan(wbs_efforts=[
        GeneratedWBSEffort(
            wbs_id=101,
            detailed_job="업무분석가",
            estimated_person_days=10,
            estimation_reason="업무 요구사항과 프로세스 분석이 필요합니다.",
            confidence=0.9,
        ),
        GeneratedWBSEffort(
            wbs_id=102,
            detailed_job="인공지능 SW 개발자",
            estimated_person_days=20,
            estimation_reason="REST API와 도메인 로직 구현이 필요합니다.",
            confidence=0.95,
        ),
        GeneratedWBSEffort(
            wbs_id=103,
            detailed_job="인공지능 SW 개발자",
            estimated_person_days=15,
            estimation_reason="외부 연동 규격 구현과 오류 처리가 필요합니다.",
            confidence=0.85,
        ),
    ], overlap_candidates=[
        GeneratedOverlapCandidate(
            wbs_ids=[102, 103],
            reason="API 구현 범위가 일부 겹칠 가능성이 있습니다.",
            recommendation="공통 인증과 오류 처리 범위를 분리해 확인하세요.",
        )
    ])


class FakeEffortLLMService:
    def generate(self, context):
        return generated_plan()


class SuccessfulEffortGraph:
    def invoke(self, request):
        return PlanningEffortGraph(
            llm_service=FakeEffortLLMService(),
        ).invoke(request)


class CapturingResponses:
    def __init__(self):
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=generated_plan())


class PlanningEffortEstimateTest(unittest.TestCase):
    def test_service_returns_wbs_reasons_and_aggregates_jobs(self):
        request = PlanningEffortEstimateRequest.model_validate(request_payload())
        result = PlanningEffortService().build_response(request, generated_plan())

        self.assertEqual(result["workdays_per_month"], 20.5)
        self.assertEqual(result["total_estimated_person_days"], 45.0)
        self.assertEqual(result["total_estimated_mm"], 2.2)
        self.assertEqual(len(result["wbs_efforts"]), 3)
        self.assertEqual(
            result["wbs_efforts"][0]["estimation_reason"],
            "업무 요구사항과 프로세스 분석이 필요합니다.",
        )

        jobs = {
            item["detailed_job"]: item for item in result["job_efforts"]
        }
        developer = jobs["인공지능 SW 개발자"]
        self.assertEqual(
            developer["kosa_job_category"],
            "응용 SW 개발자",
        )
        self.assertEqual(developer["estimated_person_days"], 35.0)
        self.assertEqual(developer["estimated_mm"], 1.71)
        self.assertEqual(developer["wbs_ids"], [102, 103])
        self.assertEqual(len(result["work_package_efforts"]), 2)
        service_package = result["work_package_efforts"][1]
        self.assertEqual(service_package["work_package_id"], 20)
        self.assertEqual(service_package["estimated_person_days"], 35.0)
        self.assertEqual(service_package["estimated_mm"], 1.71)
        self.assertEqual(result["overlap_candidates"][0]["wbs_ids"], [102, 103])

    def test_detailed_jobs_map_to_the_same_rate_category(self):
        self.assertEqual(
            DETAILED_JOB_CATEGORY[
                KosaDetailedJob.빅데이터_개발자
            ],
            KosaJobCategory.응용_소프트웨어_개발자,
        )
        self.assertEqual(
            DETAILED_JOB_CATEGORY[
                KosaDetailedJob.인공지능_소프트웨어_개발자
            ],
            KosaJobCategory.응용_소프트웨어_개발자,
        )
        self.assertEqual(
            DETAILED_JOB_CATEGORY[
                KosaDetailedJob.인공지능_서비스운용자
            ],
            KosaJobCategory.정보시스템운용자,
        )

    def test_service_rejects_missing_wbs_result(self):
        request = PlanningEffortEstimateRequest.model_validate(request_payload())
        incomplete = GeneratedEffortPlan(
            wbs_efforts=generated_plan().wbs_efforts[:2]
        )

        with self.assertRaises(InvalidEffortLLMResponseError):
            PlanningEffortService().build_response(request, incomplete)

    def test_request_rejects_duplicate_wbs_ids(self):
        payload = request_payload()
        payload["wbs_tasks"].append(payload["wbs_tasks"][0])

        with self.assertRaises(ValidationError):
            PlanningEffortEstimateRequest.model_validate(payload)

    def test_request_rejects_parent_and_child_selected_together(self):
        payload = request_payload()
        payload["wbs_tasks"].append({
            "wbs_id": 10,
            "wbs_name": "요구사항 정의",
            "description": "요구사항 작업 패키지 전체",
            "level": 2,
            "item_type": "WORK_PACKAGE",
        })

        with self.assertRaises(ValidationError):
            PlanningEffortEstimateRequest.model_validate(payload)

    def test_llm_splits_large_requests_without_mixing_package_order(self):
        service = PlanningEffortLLMService()
        tasks = [
            {
                "wbs_id": index,
                "work_package_id": 10 if index <= 20 else 20,
            }
            for index in range(1, 41)
        ]

        batches = service._split_context({"project_id": 1, "wbs_tasks": tasks})

        self.assertEqual([len(batch["wbs_tasks"]) for batch in batches], [20, 20])
        self.assertEqual(batches[0]["batch_count"], 2)
        returned_ids = [
            task["wbs_id"]
            for batch in batches
            for task in batch["wbs_tasks"]
        ]
        self.assertEqual(returned_ids, list(range(1, 41)))

    def test_llm_uses_structured_output_and_forbids_price_generation(self):
        responses = CapturingResponses()
        client = SimpleNamespace(responses=responses)
        service = PlanningEffortLLMService()

        result = service._request(client, {"wbs_tasks": []})

        self.assertIsInstance(result, GeneratedEffortPlan)
        self.assertIs(responses.request["text_format"], GeneratedEffortPlan)
        self.assertFalse(responses.request["store"])
        instructions = service._instructions()
        self.assertIn("KOSA 세부직무", instructions)
        self.assertIn("MM, 담당자, 단가", instructions)
        self.assertIn("외부 AI API를 단순 호출", instructions)

    def test_endpoint_returns_wbs_and_job_efforts(self):
        router_module = importlib.import_module(
            "app.domains.planning_costs.router"
        )
        with patch.object(
            router_module,
            "planning_effort_graph",
            SuccessfulEffortGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/costs/effort-estimate",
                json=request_payload(),
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["llm_status"], "SUCCEEDED")
        self.assertEqual(len(body["wbs_efforts"]), 3)
        self.assertEqual(len(body["job_efforts"]), 2)
        self.assertEqual(len(body["work_package_efforts"]), 2)
        self.assertEqual(len(body["overlap_candidates"]), 1)

    def test_configuration_failure_maps_to_503(self):
        class MissingKeyGraph:
            def invoke(self, request):
                raise EffortLLMConfigurationError("missing key")

        router_module = importlib.import_module(
            "app.domains.planning_costs.router"
        )
        with patch.object(
            router_module,
            "planning_effort_graph",
            MissingKeyGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/costs/effort-estimate",
                json=request_payload(),
            )

        self.assertEqual(response.status_code, 503)

    def test_openapi_describes_effort_endpoint(self):
        operation = app.openapi()["paths"][
            "/api/v1/planning/costs/effort-estimate"
        ]["post"]

        self.assertEqual(operation["summary"], "KOSA 직무별 프로젝트 공수 산정")
        self.assertIn("WBS별 상세 근거", operation["description"])


if __name__ == "__main__":
    unittest.main()
