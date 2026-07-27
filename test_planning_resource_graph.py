import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.planning_resource_graph import PlanningResourceGraph
from app.main import app
from app.schemas.planning_resource import PlanningResourceRequest
from app.services.planning_resource_llm_service import (
    GeneratedRequiredSkill,
    GeneratedResourcePlan,
    GeneratedTaskResourceEstimate,
    PlanningResourceLLMService,
    ResourceLLMConfigurationError,
)
from app.services.planning_resource_service import PlanningResourceService


def sample_request(
    *,
    second_task: bool = False,
    second_member_status: str = "ACTIVE",
) -> PlanningResourceRequest:
    tasks = [
        {
            "wbs_id": 10,
            "wbs_name": "대시보드 API 구현",
            "description": "학습 현황 조회 Spring Boot API를 구현한다.",
            "start_date": "2026-08-10",
            "end_date": "2026-08-21",
        }
    ]
    if second_task:
        tasks.append({
            "wbs_id": 11,
            "wbs_name": "학습 분석 API 구현",
            "description": "학습 분석 결과 조회 API를 구현한다.",
            "start_date": "2026-08-10",
            "end_date": "2026-08-21",
        })

    return PlanningResourceRequest.model_validate({
        "project_id": 1,
        "wbs_tasks": tasks,
        "project_members": [
            {
                "project_member_id": 101,
                "roles": ["BACKEND_DEVELOPER"],
                "skills": [
                    {
                        "skill_code": "JAVA",
                        "proficiency_level": 4,
                        "experience_months": 36,
                    },
                    {
                        "skill_code": "SPRING_BOOT",
                        "proficiency_level": 4,
                        "experience_months": 30,
                    },
                ],
                "allocations": [
                    {
                        "allocation_start_date": "2026-08-01",
                        "allocation_end_date": "2026-12-31",
                        "available_hours_per_week": 20,
                        "allocation_status": "ACTIVE",
                    }
                ],
            },
            {
                "project_member_id": 102,
                "roles": ["BACKEND_DEVELOPER"],
                "skills": [
                    {
                        "skill_code": "JAVA",
                        "proficiency_level": 3,
                        "experience_months": 20,
                    },
                    {
                        "skill_code": "SPRING_BOOT",
                        "proficiency_level": 3,
                        "experience_months": 18,
                    },
                ],
                "allocations": [
                    {
                        "allocation_start_date": "2026-08-01",
                        "allocation_end_date": "2026-09-30",
                        "available_hours_per_week": 16,
                        "allocation_status": second_member_status,
                    }
                ],
            },
        ],
    })


def estimate(wbs_id: int, person_days: float = 7) -> GeneratedTaskResourceEstimate:
    return GeneratedTaskResourceEstimate(
        wbs_id=wbs_id,
        required_role_code="BACKEND_DEVELOPER",
        required_skills=[
            GeneratedRequiredSkill(
                skill_code="JAVA",
                minimum_proficiency_level=3,
            ),
            GeneratedRequiredSkill(
                skill_code="SPRING_BOOT",
                minimum_proficiency_level=3,
            ),
        ],
        estimated_person_days=person_days,
        estimation_reason="조회 API와 데이터 가공 로직 구현이 필요합니다.",
    )


def complete_plan(second_task: bool = False) -> GeneratedResourcePlan:
    estimates = [estimate(10)]
    if second_task:
        estimates.append(estimate(11))
    return GeneratedResourcePlan(task_estimates=estimates)


class CompleteFakeLLMService:
    def generate(self, contexts):
        task_ids = [
            task["wbs_id"]
            for context in contexts
            for task in context["tasks"]
        ]
        return [GeneratedResourcePlan(
            task_estimates=[estimate(wbs_id) for wbs_id in task_ids]
        )]


class MissingKeyGraph:
    def invoke(self, request):
        raise ResourceLLMConfigurationError(
            "OPENAI_API_KEY가 설정되지 않았습니다."
        )


class SuccessfulGraph:
    def invoke(self, request):
        return PlanningResourceGraph(
            llm_service=CompleteFakeLLMService(),
        ).invoke(request)


class CapturingResponses:
    def __init__(self):
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=complete_plan())


class PlanningResourceGraphTest(unittest.TestCase):
    def build_graph(self):
        return PlanningResourceGraph(
            llm_service=CompleteFakeLLMService(),
        )

    def test_graph_calculates_mm_and_recommends_multiple_members(self):
        result = self.build_graph().invoke(sample_request())

        self.assertEqual(result["project_id"], 1)
        self.assertEqual(result["total_estimated_person_days"], 7.0)
        self.assertEqual(result["total_estimated_hours"], 56.0)
        self.assertEqual(result["total_estimated_mm"], 0.35)

        assignment = result["assignments"][0]
        self.assertEqual(assignment["required_headcount"], 2)
        self.assertEqual(
            [item["project_member_id"] for item in assignment["recommended_members"]],
            [101, 102],
        )
        self.assertEqual(
            [item["assigned_hours"] for item in assignment["recommended_members"]],
            [40.0, 16.0],
        )
        self.assertEqual(result["unassigned_wbs_ids"], [])
        self.assertEqual(result["required_staffing"][0]["shortage_count"], 0)

    def test_paused_member_is_excluded_and_shortage_is_reported(self):
        result = self.build_graph().invoke(sample_request(
            second_member_status="PAUSED",
        ))

        assignment = result["assignments"][0]
        self.assertEqual(
            [item["project_member_id"] for item in assignment["recommended_members"]],
            [101],
        )
        self.assertEqual(result["unassigned_wbs_ids"], [10])
        self.assertEqual(result["required_staffing"][0]["shortage_count"], 1)
        self.assertTrue(any("16.0시간" in warning for warning in result["warnings"]))

    def test_overlapping_tasks_do_not_reuse_same_member_capacity(self):
        result = self.build_graph().invoke(sample_request(second_task=True))

        first, second = result["assignments"]
        first_assigned = sum(
            member["assigned_hours"] for member in first["recommended_members"]
        )
        second_assigned = sum(
            member["assigned_hours"] for member in second["recommended_members"]
        )
        self.assertEqual(first_assigned, 56.0)
        self.assertEqual(second_assigned, 16.0)
        self.assertEqual(result["unassigned_wbs_ids"], [11])

    def test_constrained_task_is_assigned_before_flexible_task(self):
        payload = sample_request(second_task=True).model_dump(mode="json")
        payload["wbs_tasks"][0].update({
            "start_date": "2026-08-10",
            "end_date": "2026-08-21",
        })
        payload["wbs_tasks"][1].update({
            "start_date": "2026-08-12",
            "end_date": "2026-08-18",
        })
        payload["project_members"] = [payload["project_members"][0]]
        payload["project_members"][0]["allocations"][0][
            "available_hours_per_week"
        ] = 40
        request = PlanningResourceRequest.model_validate(payload)
        plan = GeneratedResourcePlan(task_estimates=[
            estimate(10, person_days=5),
            estimate(11, person_days=5),
        ])

        result = PlanningResourceService().build_recommendation(
            request,
            [plan],
        )

        self.assertEqual(result["unassigned_wbs_ids"], [])
        by_id = {
            assignment["wbs_id"]: assignment
            for assignment in result["assignments"]
        }
        self.assertEqual(
            by_id[10]["recommended_members"][0]["assigned_hours"],
            40.0,
        )
        self.assertEqual(
            by_id[11]["recommended_members"][0]["assigned_hours"],
            40.0,
        )

    def test_available_candidate_count_uses_skill_and_task_period(self):
        payload = sample_request().model_dump(mode="json")
        payload["project_members"][0]["skills"][0]["proficiency_level"] = 2
        payload["project_members"][1]["allocations"][0][
            "allocation_end_date"
        ] = "2026-08-09"
        request = PlanningResourceRequest.model_validate(payload)

        result = PlanningResourceService().build_recommendation(
            request,
            [complete_plan()],
        )

        self.assertEqual(
            result["required_staffing"][0]["available_candidate_count"],
            0,
        )
        self.assertEqual(
            result["assignments"][0]["recommended_members"],
            [],
        )
        self.assertEqual(result["unassigned_wbs_ids"], [10])

    def test_more_experienced_member_receives_higher_score(self):
        result = self.build_graph().invoke(sample_request())
        members = result["assignments"][0]["recommended_members"]
        self.assertGreater(
            members[0]["recommendation_score"],
            members[1]["recommendation_score"],
        )

    def test_allocation_outside_task_period_is_not_used(self):
        payload = sample_request().model_dump(mode="json")
        for member in payload["project_members"]:
            member["allocations"][0]["allocation_end_date"] = "2026-08-09"
        request = PlanningResourceRequest.model_validate(payload)

        result = self.build_graph().invoke(request)

        self.assertEqual(result["assignments"][0]["recommended_members"], [])
        self.assertEqual(result["unassigned_wbs_ids"], [10])

    def test_request_rejects_duplicate_ids(self):
        payload = sample_request().model_dump(mode="json")
        payload["wbs_tasks"].append(payload["wbs_tasks"][0])
        with self.assertRaises(ValidationError):
            PlanningResourceRequest.model_validate(payload)

    def test_tasks_are_split_into_thirty_item_batches(self):
        payload = sample_request().model_dump(mode="json")
        template = payload["wbs_tasks"][0]
        payload["wbs_tasks"] = [
            {**template, "wbs_id": index}
            for index in range(1, 32)
        ]
        request = PlanningResourceRequest.model_validate(payload)

        contexts = PlanningResourceService().prepare_contexts(request)

        self.assertEqual([len(context["tasks"]) for context in contexts], [30, 1])

    def test_openai_request_uses_pydantic_structured_output(self):
        responses = CapturingResponses()
        fake_client = SimpleNamespace(responses=responses)
        service = PlanningResourceLLMService()

        result = service._request_one(fake_client, {"tasks": [{"wbs_id": 10}]})

        self.assertIsInstance(result, GeneratedResourcePlan)
        self.assertIs(
            responses.request["text_format"],
            GeneratedResourcePlan,
        )
        self.assertFalse(responses.request["store"])

    def test_fastapi_returns_resource_recommendation(self):
        payload = sample_request().model_dump(mode="json")
        with patch.object(
            importlib.import_module("app.main"),
            "planning_resource_graph",
            SuccessfulGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/resources/recommend",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_id"], 1)
        self.assertEqual(body["assignments"][0]["wbs_id"], 10)

    def test_fastapi_returns_503_when_api_key_is_missing(self):
        payload = sample_request().model_dump(mode="json")
        with patch.object(
            importlib.import_module("app.main"),
            "planning_resource_graph",
            MissingKeyGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/resources/recommend",
                json=payload,
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_openapi_describes_resource_endpoint_in_korean(self):
        operation = app.openapi()["paths"][
            "/api/v1/planning/resources/recommend"
        ]["post"]
        self.assertEqual(operation["summary"], "프로젝트 필요 인력·담당자·MM 추천")
        self.assertIn("주간 가용시간", operation["description"])

        schemas = app.openapi()["components"]["schemas"]
        self.assertEqual(
            schemas["PlanningResourceRequest"]["properties"]["project_id"]["type"],
            "integer",
        )
        self.assertEqual(
            schemas["ProjectMemberCandidate"]["properties"][
                "project_member_id"
            ]["type"],
            "integer",
        )


if __name__ == "__main__":
    unittest.main()
