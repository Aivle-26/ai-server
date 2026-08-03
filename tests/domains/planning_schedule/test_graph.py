import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domains.planning_schedule.graph import PlanningScheduleGraph
from app.domains.planning_schedule.llm_service import (
    GeneratedSchedulePlan,
    GeneratedTaskScheduleEstimate,
    PlanningScheduleLLMService,
    ScheduleLLMConfigurationError,
)
from app.domains.planning_schedule.schemas import PlanningScheduleRequest
from app.domains.planning_schedule.service import PlanningScheduleService
from app.main import app


def sample_request(
    *,
    project_start_date: str = "2026-08-03",
    target_end_date: str | None = "2026-12-31",
) -> PlanningScheduleRequest:
    return PlanningScheduleRequest.model_validate({
        "project_id": 1,
        "project_start_date": project_start_date,
        "target_end_date": target_end_date,
        "wbs_items": [
            {
                "wbs_id": 1,
                "wbs_code": "1",
                "parent_wbs_id": None,
                "item_type": "PHASE",
                "wbs_name": "요구사항 분석",
                "description": "프로젝트 요구사항을 분석한다.",
            },
            {
                "wbs_id": 2,
                "wbs_code": "1.1",
                "parent_wbs_id": 1,
                "item_type": "WORK_PACKAGE",
                "wbs_name": "기능 요구사항 분석",
                "description": "기능 요구사항을 상세화한다.",
            },
            {
                "wbs_id": 3,
                "wbs_code": "1.1.1",
                "parent_wbs_id": 2,
                "item_type": "TASK",
                "wbs_name": "요구사항 후보 추출",
                "description": "초기 문서에서 요구사항 후보를 추출한다.",
            },
            {
                "wbs_id": 4,
                "wbs_code": "1.1.2",
                "parent_wbs_id": 2,
                "item_type": "TASK",
                "wbs_name": "요구사항 검토",
                "description": "추출된 요구사항을 검토하고 확정한다.",
            },
            {
                "wbs_id": 5,
                "wbs_code": "2",
                "parent_wbs_id": None,
                "item_type": "PHASE",
                "wbs_name": "개발",
                "description": "승인된 요구사항을 구현한다.",
            },
            {
                "wbs_id": 6,
                "wbs_code": "2.1",
                "parent_wbs_id": 5,
                "item_type": "WORK_PACKAGE",
                "wbs_name": "대시보드 개발",
                "description": "대시보드 기능을 개발한다.",
            },
            {
                "wbs_id": 7,
                "wbs_code": "2.1.1",
                "parent_wbs_id": 6,
                "item_type": "TASK",
                "wbs_name": "대시보드 구현",
                "description": "학습 현황 대시보드를 구현한다.",
            },
        ],
    })


def complete_plan() -> GeneratedSchedulePlan:
    return GeneratedSchedulePlan(task_estimates=[
        GeneratedTaskScheduleEstimate(
            wbs_id=3,
            optimistic_days=2,
            most_likely_days=3,
            pessimistic_days=5,
            predecessor_wbs_ids=[],
        ),
        GeneratedTaskScheduleEstimate(
            wbs_id=4,
            optimistic_days=1,
            most_likely_days=2,
            pessimistic_days=4,
            predecessor_wbs_ids=[3],
            milestone=True,
            buffer_days=2,
        ),
        GeneratedTaskScheduleEstimate(
            wbs_id=7,
            optimistic_days=4,
            most_likely_days=6,
            pessimistic_days=10,
            predecessor_wbs_ids=[],
        ),
    ])


class CompleteFakeLLMService:
    def generate(self, context):
        return complete_plan()


class MissingEstimateFakeLLMService:
    def generate(self, context):
        return GeneratedSchedulePlan(task_estimates=[
            complete_plan().task_estimates[0],
        ])


class MissingKeyGraph:
    def invoke(self, request):
        raise ScheduleLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")


class SuccessfulGraph:
    def invoke(self, request):
        return PlanningScheduleGraph(
            schedule_service=PlanningScheduleService(
                monte_carlo_iterations=200,
                random_seed=7,
            ),
            llm_service=CompleteFakeLLMService(),
        ).invoke(request)


class CapturingResponses:
    def __init__(self):
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=complete_plan())


class PlanningScheduleGraphTest(unittest.TestCase):
    def build_graph(self, llm_service=None):
        return PlanningScheduleGraph(
            schedule_service=PlanningScheduleService(
                monte_carlo_iterations=300,
                random_seed=42,
            ),
            llm_service=llm_service or CompleteFakeLLMService(),
        )

    def test_graph_returns_three_schedule_versions_for_every_wbs(self):
        request = sample_request()
        result = self.build_graph().invoke(request)

        self.assertEqual(result["project_id"], 1)
        self.assertEqual(len(result["wbs_schedules"]), len(request.wbs_items))
        for schedule in result["wbs_schedules"]:
            self.assertEqual(
                set(schedule),
                {
                    "wbs_id", "expected", "recommended", "conservative",
                    "predecessor_wbs_ids", "milestone", "buffer_days",
                },
            )
            expected_end = date.fromisoformat(
                schedule["expected"]["end_date"].isoformat()
                if isinstance(schedule["expected"]["end_date"], date)
                else schedule["expected"]["end_date"]
            )
            recommended_end = schedule["recommended"]["end_date"]
            conservative_end = schedule["conservative"]["end_date"]
            expected_start = schedule["expected"]["start_date"]
            recommended_start = schedule["recommended"]["start_date"]
            conservative_start = schedule["conservative"]["start_date"]
            self.assertLessEqual(expected_start, recommended_start)
            self.assertLessEqual(recommended_start, conservative_start)
            self.assertLessEqual(expected_end, recommended_end)
            self.assertLessEqual(recommended_end, conservative_end)

    def test_predecessor_and_phase_order_are_applied(self):
        result = self.build_graph().invoke(sample_request())
        by_id = {
            item["wbs_id"]: item
            for item in result["wbs_schedules"]
        }

        for policy in ("expected", "recommended", "conservative"):
            self.assertGreater(
                by_id[4][policy]["start_date"],
                by_id[3][policy]["end_date"],
            )
            self.assertGreater(
                by_id[7][policy]["start_date"],
                by_id[4][policy]["end_date"],
            )
        self.assertEqual(by_id[4]["predecessor_wbs_ids"], [3])
        self.assertEqual(by_id[3]["predecessor_wbs_ids"], [])
        self.assertTrue(by_id[4]["milestone"])
        self.assertEqual(by_id[4]["buffer_days"], 2)

    def test_parent_schedule_is_rolled_up_from_child_tasks(self):
        result = self.build_graph().invoke(sample_request())
        by_id = {
            item["wbs_id"]: item
            for item in result["wbs_schedules"]
        }

        for policy in ("expected", "recommended", "conservative"):
            self.assertEqual(
                by_id[1][policy]["start_date"],
                by_id[3][policy]["start_date"],
            )
            self.assertEqual(
                by_id[1][policy]["end_date"],
                by_id[4][policy]["end_date"],
            )

    def test_weekend_project_start_is_moved_to_monday(self):
        result = self.build_graph().invoke(sample_request(
            project_start_date="2026-08-01",
        ))
        by_id = {
            item["wbs_id"]: item
            for item in result["wbs_schedules"]
        }
        self.assertEqual(
            by_id[3]["expected"]["start_date"],
            date(2026, 8, 3),
        )

    def test_missing_estimate_uses_default_and_returns_warning(self):
        result = self.build_graph(MissingEstimateFakeLLMService()).invoke(
            sample_request()
        )
        self.assertTrue(any(
            "기간 추정이 누락되어 기본 기간을 적용했습니다." in warning
            for warning in result["warnings"]
        ))

    def test_target_end_overrun_returns_warning(self):
        result = self.build_graph().invoke(sample_request(
            target_end_date="2026-08-10",
        ))
        self.assertTrue(any(
            "목표 종료일을 초과합니다" in warning
            for warning in result["warnings"]
        ))

    def test_same_input_returns_same_monte_carlo_result(self):
        graph = self.build_graph()
        first = graph.invoke(sample_request())
        second = graph.invoke(sample_request())
        self.assertEqual(first, second)

    def test_request_rejects_invalid_hierarchy(self):
        payload = sample_request().model_dump(mode="json")
        payload["wbs_items"][2]["parent_wbs_id"] = 5
        with self.assertRaises(ValidationError):
            PlanningScheduleRequest.model_validate(payload)

    def test_request_accepts_extra_fields_from_existing_wbs_response(self):
        payload = sample_request().model_dump(mode="json")
        payload["wbs_items"][2].update({
            "level": 3,
            "sort_order": 1,
            "mapped_requirement_ids": [1],
            "related_artifacts": [],
            "completion_criteria": ["요구사항 검토 완료"],
        })
        request = PlanningScheduleRequest.model_validate(payload)
        self.assertEqual(request.wbs_items[2].wbs_id, 3)

    def test_openai_request_uses_pydantic_structured_output(self):
        responses = CapturingResponses()
        fake_client = SimpleNamespace(responses=responses)
        service = PlanningScheduleLLMService()

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch(
                "app.domains.planning_schedule.llm_service.OpenAI",
                return_value=fake_client,
            ),
        ):
            result = service.generate({"tasks": [{"wbs_id": 3}]})

        self.assertEqual(len(result.task_estimates), 3)
        self.assertIs(
            responses.request["text_format"],
            GeneratedSchedulePlan,
        )
        self.assertFalse(responses.request["store"])

    def test_fastapi_returns_generated_schedule(self):
        payload = sample_request().model_dump(mode="json")
        with patch(
            "app.domains.planning_schedule.router.planning_schedule_graph",
            SuccessfulGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/schedules/recommend",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_id"], 1)
        self.assertEqual(len(body["wbs_schedules"]), 7)

    def test_fastapi_returns_503_when_api_key_is_missing(self):
        payload = sample_request().model_dump(mode="json")
        with patch(
            "app.domains.planning_schedule.router.planning_schedule_graph",
            MissingKeyGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/schedules/recommend",
                json=payload,
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["message"])

    def test_openapi_describes_schedule_endpoint_in_korean(self):
        operation = app.openapi()["paths"][
            "/api/v1/planning/schedules/recommend"
        ]["post"]
        self.assertEqual(operation["summary"], "WBS 기반 프로젝트 일정 추천")
        self.assertIn("예상·권장·보수적", operation["description"])


if __name__ == "__main__":
    unittest.main()
