import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.project_risk.router import impact_llm_service
from app.domains.project_risk.services.impact_llm_service import (
    GeneratedImpactAnalysis,
    ImpactLLMConfigurationError,
    LLMAffectedTask,
)
from app.main import app


def sample_wbs_tasks():
    return [
        {
            "task_id": 1,
            "task_name": "로그인 API 구현",
            "assignee": "김개발",
            "status": "IN_PROGRESS",
            "estimated_days": 5,
        },
        {
            "task_id": 2,
            "task_name": "회원 DB 스키마 설계",
            "assignee": "이디비",
            "status": "TODO",
            "estimated_days": 3,
        },
        {
            "task_id": 3,
            "task_name": "관리자 대시보드 UI",
            "assignee": "김개발",
            "status": "TODO",
            "estimated_days": 4,
        },
    ]


class ImpactLLMEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_backward_compatible_rule_based_path(self):
        # wbs_tasks 없이 기존 방식으로 호출 → 기존 규칙식 결과 유지
        response = self.client.post(
            "/api/v1/risk/impact-assessment",
            json={
                "project_id": 7,
                "requirement_id": 10,
                "change_title": "Scope update",
                "change_description": "Add a new workflow",
                "affected_task_count": 5,
                "affected_member_count": 4,
                "remaining_days": 10,
                "additional_work_days": 20,
                "scope_changed": True,
                "database_changed": True,
                "api_changed": True,
                "ui_changed": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["impact_score"], 79)
        self.assertEqual(body["impact_level"], "HIGH")
        self.assertEqual(body["llm_status"], "DISABLED")
        # 응답에 산출 수치가 그대로 반영되어야 함
        self.assertEqual(body["affected_task_count"], 5)
        self.assertEqual(body["additional_work_days"], 20)

    def test_llm_auto_fills_numbers(self):
        fake = GeneratedImpactAnalysis(
            affected_tasks=[
                LLMAffectedTask(
                    task_id=1,
                    impact_type="DIRECT",
                    additional_work_days=4,
                    reason="로그인 로직 수정 필요",
                ),
                LLMAffectedTask(
                    task_id=2,
                    impact_type="INDIRECT",
                    additional_work_days=2,
                    reason="스키마 컬럼 추가",
                ),
                # 존재하지 않는 id → 필터링되어야 함(환각 방지)
                LLMAffectedTask(
                    task_id=999,
                    impact_type="DIRECT",
                    additional_work_days=10,
                    reason="지어낸 태스크",
                ),
                # NONE → 제외되어야 함
                LLMAffectedTask(
                    task_id=3,
                    impact_type="NONE",
                    additional_work_days=0,
                    reason="영향 없음",
                ),
            ],
            scope_changed=True,
            database_changed=True,
            api_changed=False,
            ui_changed=False,
            summary="로그인과 회원 스키마에 영향이 있습니다.",
        )

        with patch.object(impact_llm_service, "analyze", return_value=fake):
            response = self.client.post(
                "/api/v1/risk/impact-assessment",
                json={
                    "project_id": 7,
                    "change_title": "로그인에 소셜 로그인 추가",
                    "change_description": "카카오/구글 소셜 로그인을 추가한다.",
                    "wbs_tasks": sample_wbs_tasks(),
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["llm_status"], "SUCCEEDED")
        # id 999(환각), id 3(NONE) 제외 → 2건만
        self.assertEqual(body["affected_task_count"], 2)
        # 추가 작업일 합계 4+2 = 6 (환각 태스크 10은 제외)
        self.assertEqual(body["additional_work_days"], 6)
        # 영향 태스크 담당자 distinct: 김개발, 이디비 → 2
        self.assertEqual(body["affected_member_count"], 2)
        self.assertTrue(body["scope_changed"])
        self.assertTrue(body["database_changed"])
        self.assertEqual(len(body["affected_tasks"]), 2)
        self.assertEqual(body["ai_summary"], "로그인과 회원 스키마에 영향이 있습니다.")

    def test_remaining_days_auto_computed(self):
        fake = GeneratedImpactAnalysis(
            affected_tasks=[],
            summary="영향 없음",
        )
        with patch.object(impact_llm_service, "analyze", return_value=fake):
            response = self.client.post(
                "/api/v1/risk/impact-assessment",
                json={
                    "project_id": 7,
                    "change_title": "사소한 변경",
                    "change_description": "문구 수정",
                    "wbs_tasks": sample_wbs_tasks(),
                    "evaluation_date": "2026-08-05",
                    "project_end_date": "2026-08-20",
                },
            )
        self.assertEqual(response.status_code, 200)
        # 2026-08-20 - 2026-08-05 = 15일
        self.assertEqual(response.json()["remaining_days"], 15)

    def test_fallback_when_no_api_key(self):
        def raise_config_error(context):
            raise ImpactLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")

        with patch.object(impact_llm_service, "analyze", side_effect=raise_config_error):
            response = self.client.post(
                "/api/v1/risk/impact-assessment",
                json={
                    "project_id": 7,
                    "change_title": "변경",
                    "change_description": "설명",
                    "wbs_tasks": sample_wbs_tasks(),
                    # fallback으로 쓰일 수동 입력값
                    "affected_task_count": 2,
                    "affected_member_count": 1,
                    "additional_work_days": 3,
                    "remaining_days": 10,
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["llm_status"], "SKIPPED_NO_API_KEY")
        # 수동 입력값으로 fallback
        self.assertEqual(body["affected_task_count"], 2)
        self.assertEqual(body["additional_work_days"], 3)


if __name__ == "__main__":
    unittest.main()
