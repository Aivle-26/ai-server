import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.planning_wbs_graph import PlanningWBSGraph
from app.main import app
from app.schemas.planning_wbs import WBSGenerationRequest
from app.services.planning_wbs_llm_service import (
    GeneratedWBSPhase,
    GeneratedWBSPlan,
    GeneratedWBSTask,
    GeneratedWBSWorkPackage,
    PlanningWBSLLMService,
    WBSLLMConfigurationError,
)
from app.services.planning_wbs_service import PlanningWBSService


def sample_request(methodology=None, requirement_count=2) -> WBSGenerationRequest:
    requirements = []
    for index in range(1, requirement_count + 1):
        requirements.append({
            "requirement_id": index,
            "function_name": "학습 현황 대시보드" if index == 1 else f"보안 기능 {index}",
            "requirement_text": (
                "학생별 학습 현황을 조회할 수 있어야 한다."
                if index == 1
                else f"보안 요구사항 {index}을 적용해야 한다."
            ),
            "category": "FUNCTIONAL" if index == 1 else "SECURITY",
            "priority": "HIGH",
            "acceptance_criteria": "요구사항 검수 조건 충족",
            "due_date": "2026-10-31",
            "deliverable_name": "기능 명세서",
            "security_condition": None if index == 1 else "보안 조건 적용",
            "source_document": "RFP.hwp",
            "source_excerpt": "원문 근거",
        })
    return WBSGenerationRequest.model_validate({
        "project_info": {
            "project_name": "AI 학습지원시스템 구축",
            "project_goal": "맞춤형 학습 지원",
            "client_organization": "OO대학교",
            "period_start": "2026-08-01",
            "period_end": "2026-12-31",
            "key_features": ["대시보드", "보안"],
            "required_artifacts": [
                {
                    "artifact_type": "REQUIREMENTS_DEFINITION",
                    "artifact_name": "요구사항 정의서",
                    "required_version": "1.0",
                },
                {
                    "artifact_type": "FUNCTION_SPECIFICATION",
                    "artifact_name": "기능 명세서",
                    "required_version": "1.0",
                },
            ],
            "acceptance_conditions": ["기능 테스트 통과"],
            "budget_contract_conditions": [],
            "security_privacy_conditions": ["개인정보 암호화"],
        },
        "requirement_candidates": requirements,
        "methodology": methodology or ["요구사항 분석", "개발"],
    })


def task(name, requirement_ids, artifact_types):
    return GeneratedWBSTask(
        name=name,
        description=f"{name}을 수행한다.",
        mapped_requirement_ids=requirement_ids,
        related_artifact_types=artifact_types,
        completion_criteria=[f"{name} 완료"],
    )


def phase(name, package_name, tasks):
    return GeneratedWBSPhase(
        phase_name=name,
        description=f"{name} 단계",
        completion_criteria=[f"{name} 단계 완료"],
        work_packages=[GeneratedWBSWorkPackage(
            name=package_name,
            description=f"{package_name} 작업 묶음",
            completion_criteria=[f"{package_name} 완료"],
            tasks=tasks,
        )],
    )


def complete_plan():
    return GeneratedWBSPlan(phases=[
        phase(
            "요구사항 분석",
            "요구사항 상세화",
            [task(
                "프로젝트 요구사항 상세화",
                [1, 2],
                ["REQUIREMENTS_DEFINITION"],
            )],
        ),
        phase(
            "개발",
            "기능 구현",
            [task(
                "대시보드 및 보안 기능 구현",
                [1, 2],
                ["FUNCTION_SPECIFICATION"],
            )],
        ),
    ])


class CompleteFakeLLMService:
    def generate(self, contexts):
        return [complete_plan()]


class RepairingFakeLLMService:
    def __init__(self):
        self.contexts = []

    def generate(self, contexts):
        self.contexts.append(contexts)
        if len(self.contexts) == 1:
            return [GeneratedWBSPlan(phases=[phase(
                "요구사항 분석",
                "기능 요구사항 분석",
                [task(
                    "대시보드 요구사항 상세화",
                    [1],
                    ["REQUIREMENTS_DEFINITION"],
                )],
            )])]
        return [GeneratedWBSPlan(phases=[phase(
            "개발",
            "누락 기능 구현",
            [task(
                "보안 기능 구현",
                [2],
                ["FUNCTION_SPECIFICATION"],
            )],
        )])]


class PartialFakeLLMService:
    def generate(self, contexts):
        return [GeneratedWBSPlan(phases=[phase(
            "요구사항 분석",
            "기능 요구사항 분석",
            [task(
                "대시보드 요구사항 상세화",
                [1],
                ["REQUIREMENTS_DEFINITION"],
            )],
        )])]


class MissingKeyGraph:
    def invoke(self, request):
        raise WBSLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")


class CapturingResponses:
    def __init__(self):
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(output_parsed=complete_plan())


class PlanningWBSGraphTest(unittest.TestCase):
    def test_graph_generates_three_level_wbs_and_coverage(self):
        result = PlanningWBSGraph(llm_service=CompleteFakeLLMService()).invoke(
            sample_request()
        )

        self.assertEqual(result["generation_status"], "SUCCEEDED")
        self.assertEqual(result["requirement_coverage"]["coverage_rate"], 100.0)
        self.assertEqual(result["artifact_coverage"]["coverage_rate"], 100.0)
        self.assertEqual(
            [item["wbs_code"] for item in result["wbs_items"]],
            ["1", "1.1", "1.1.1", "2", "2.1", "2.1.1"],
        )
        self.assertEqual(result["wbs_items"][2]["parent_wbs_id"], 2)
        self.assertEqual(result["wbs_items"][0]["mapped_requirement_ids"], [
            1,
            2,
        ])

    def test_graph_repairs_missing_requirements_artifacts_and_phase_once(self):
        llm_service = RepairingFakeLLMService()
        result = PlanningWBSGraph(llm_service=llm_service).invoke(sample_request())

        self.assertEqual(len(llm_service.contexts), 2)
        repair_context = llm_service.contexts[1][0]
        self.assertEqual(repair_context["generation_mode"], "REPAIR")
        self.assertEqual(repair_context["target_phase_names"], ["개발"])
        self.assertEqual(
            [item["requirement_id"] for item in repair_context["requirements"]],
            [2],
        )
        self.assertEqual(result["generation_status"], "SUCCEEDED")

    def test_graph_returns_partial_when_repair_still_has_gaps(self):
        result = PlanningWBSGraph(llm_service=PartialFakeLLMService()).invoke(
            sample_request()
        )

        self.assertEqual(result["generation_status"], "PARTIAL")
        self.assertEqual(result["requirement_coverage"]["unmapped_requirement_ids"], [
            2
        ])
        self.assertIn("개발 단계에 수행 가능한 TASK가 없습니다.", result["warnings"])

    def test_request_rejects_duplicate_requirement_ids(self):
        payload = sample_request().model_dump(mode="json")
        payload["requirement_candidates"].append(payload["requirement_candidates"][0])
        with self.assertRaises(ValidationError):
            WBSGenerationRequest.model_validate(payload)

    def test_llm_context_excludes_schedule_source_and_assignment_fields(self):
        contexts = PlanningWBSService().prepare_contexts(sample_request())
        requirement = contexts[0]["requirements"][0]
        project = contexts[0]["project"]

        self.assertNotIn("due_date", requirement)
        self.assertNotIn("source_document", requirement)
        self.assertNotIn("source_excerpt", requirement)
        self.assertNotIn("period_start", project)
        self.assertNotIn("period_end", project)
        self.assertNotIn("team_members", contexts[0])

    def test_requirements_are_split_into_thirty_item_batches(self):
        contexts = PlanningWBSService().prepare_contexts(
            sample_request(requirement_count=31)
        )
        self.assertEqual(len(contexts), 2)
        self.assertEqual([len(item["requirements"]) for item in contexts], [30, 1])

    def test_openai_request_uses_pydantic_structured_output(self):
        responses = CapturingResponses()
        client = SimpleNamespace(responses=responses)

        result = PlanningWBSLLMService()._request_one(client, {"requirements": []})

        self.assertIsInstance(result, GeneratedWBSPlan)
        self.assertIs(responses.request["text_format"], GeneratedWBSPlan)
        self.assertFalse(responses.request["store"])

    def test_fastapi_returns_generated_wbs(self):
        test_graph = PlanningWBSGraph(llm_service=CompleteFakeLLMService())
        with patch.object(importlib.import_module("app.main"), "planning_wbs_graph", test_graph):
            response = TestClient(app).post(
                "/api/v1/planning/wbs/generate",
                json=sample_request().model_dump(mode="json"),
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_name"], "AI 학습지원시스템 구축")
        self.assertEqual(body["generation_status"], "SUCCEEDED")

    def test_fastapi_returns_503_when_api_key_is_missing(self):
        with patch.object(
            importlib.import_module("app.main"),
            "planning_wbs_graph",
            MissingKeyGraph(),
        ):
            response = TestClient(app).post(
                "/api/v1/planning/wbs/generate",
                json=sample_request().model_dump(mode="json"),
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_openapi_describes_wbs_in_korean_without_schedule_or_assignee(self):
        schema = app.openapi()
        operation = schema["paths"]["/api/v1/planning/wbs/generate"]["post"]
        self.assertEqual(operation["summary"], "프로젝트 WBS 작업분해구조 생성")
        properties = schema["components"]["schemas"]["WBSItem"]["properties"]
        for excluded in (
            "start_date",
            "end_date",
            "duration_days",
            "estimated_hours",
            "predecessor_ids",
            "assignee",
            "assignee_role",
            "progress_rate",
        ):
            self.assertNotIn(excluded, properties)


if __name__ == "__main__":
    unittest.main()
