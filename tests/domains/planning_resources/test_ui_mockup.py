from __future__ import annotations

import base64
import json
import os
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image, ImageFont
from pydantic import ValidationError

from app.domains.planning_resources.ui_mockup import (
    UiMockupGenerationRequest,
    UiMockupNecessityDecision,
    UiMockupSpec,
    render_ui_mockup,
)
from app.domains.planning_resources.ui_mockup_service import (
    UiMockupLLMGenerationError,
    UiMockupLLMService,
)
from app.main import app


def request_payload() -> dict:
    return {
        "project_id": 17,
        "project_title": "AIPM 프로젝트 관리 플랫폼",
        "project_description": "요구사항과 프로젝트 계획을 통합 관리합니다.",
        "confirmed_requirements": [
            {
                "requirement_id": 1,
                "title": "프로젝트 대시보드",
                "description": "진행률과 주요 일정을 한 화면에서 확인합니다.",
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            },
            {
                "requirement_id": 2,
                "title": "요구사항 관리",
                "description": "확정 요구사항을 조회하고 상태를 관리합니다.",
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            },
        ],
    }


def mockup_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "AIPM 프로젝트 관리 플랫폼",
            "design_summary": "핵심 업무를 빠르게 파악하는 밝은 업무용 화면",
            "screens": [
                {
                    "screen_name": "프로젝트 대시보드",
                    "purpose": "진행 상태와 주요 업무를 요약합니다.",
                    "navigation": ["대시보드", "요구사항", "WBS"],
                    "sections": [
                        {
                            "title": "프로젝트 현황",
                            "component_type": "card",
                            "items": ["전체 진행률", "지연 작업", "다가오는 일정"],
                        },
                        {
                            "title": "주간 진행 추이",
                            "component_type": "chart",
                            "items": [],
                        },
                    ],
                    "primary_actions": ["새 작업", "보고서 보기"],
                },
                {
                    "screen_name": "요구사항 관리",
                    "purpose": "확정 요구사항과 상태를 확인합니다.",
                    "navigation": ["전체", "확정", "검토"],
                    "sections": [
                        {
                            "title": "확정 요구사항",
                            "component_type": "table",
                            "items": ["기능명", "우선순위", "상태"],
                        }
                    ],
                    "primary_actions": ["요구사항 보기"],
                },
            ],
        }
    )


def usable_font_path() -> Path:
    windows_font = Path("C:/Windows/Fonts/malgun.ttf")
    if windows_font.is_file():
        return windows_font
    return Path(ImageFont.truetype("DejaVuSans.ttf", 12).path)


class StubUiMockupService:
    def generate(self, request: UiMockupGenerationRequest) -> UiMockupSpec:
        return mockup_spec()

    def assess(
        self,
        request: UiMockupGenerationRequest,
    ) -> UiMockupNecessityDecision:
        return UiMockupNecessityDecision(
            decision="REQUIRED",
            reason="로그인과 대시보드 화면 상호작용이 명시되어 UI 목업이 필요합니다.",
            evidence_requirement_ids=[1, 2],
            candidate_screens=["로그인", "프로젝트 대시보드"],
        )


def assessment_payload(*descriptions: str) -> dict:
    payload = request_payload()
    payload["confirmed_requirements"] = [
        {
            "requirement_id": index,
            "title": f"확정 요구사항 {index}",
            "description": description,
            "category": "FUNCTIONAL",
            "priority": "HIGH",
        }
        for index, description in enumerate(descriptions, start=1)
    ]
    return payload


class UiMockupTest(unittest.TestCase):
    def test_request_requires_confirmed_requirements(self):
        payload = request_payload()
        payload["confirmed_requirements"] = []
        with self.assertRaises(ValidationError):
            UiMockupGenerationRequest.model_validate(payload)

    def test_spec_rejects_more_than_three_screens(self):
        payload = mockup_spec().model_dump()
        payload["screens"] = payload["screens"] * 2
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(payload)

    def test_representative_korean_fixture_renders_jpeg(self):
        with patch(
            "app.domains.planning_resources.ui_mockup._resolve_font_path",
            return_value=usable_font_path(),
        ):
            rendered = render_ui_mockup(mockup_spec())
        self.assertTrue(rendered.content.startswith(b"\xff\xd8\xff"))
        image = Image.open(BytesIO(rendered.content))
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(image.size, (1920, 1080))

    def test_endpoint_returns_validated_spec_and_base64_jpeg(self):
        client = TestClient(app)
        with (
            patch(
                "app.domains.planning_resources.ui_mockup_router.ui_mockup_service",
                StubUiMockupService(),
            ),
            patch(
                "app.domains.planning_resources.ui_mockup._resolve_font_path",
                return_value=usable_font_path(),
            ),
        ):
            response = client.post(
                "/api/v1/planning/ui-mockup/generate",
                json=request_payload(),
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_id"], 17)
        self.assertGreaterEqual(len(body["mockup"]["screens"]), 1)
        self.assertLessEqual(len(body["mockup"]["screens"]), 3)
        self.assertTrue(base64.b64decode(body["image_base64"]).startswith(b"\xff\xd8\xff"))

    def test_assessment_fixtures_use_structured_output(self):
        fixtures = [
            (
                assessment_payload(
                    "사용자는 로그인해야 합니다.",
                    "대시보드에서 진행률을 확인합니다.",
                    "프로젝트 정보를 입력 폼으로 등록합니다.",
                ),
                {
                    "decision": "REQUIRED",
                    "reason": "로그인, 대시보드, 입력 폼이 명시되어 UI 목업이 필요합니다.",
                    "evidence_requirement_ids": [1, 2, 3],
                    "candidate_screens": ["로그인", "대시보드", "프로젝트 등록"],
                },
            ),
            (
                assessment_payload(
                    "내부 운영자가 처리 결과를 확인할 수 있어야 합니다.",
                ),
                {
                    "decision": "RECOMMENDED",
                    "reason": "운영자의 결과 확인 흐름이 있어 간단한 화면 구조 검토가 권장됩니다.",
                    "evidence_requirement_ids": [1],
                    "candidate_screens": ["처리 결과 확인"],
                },
            ),
            (
                assessment_payload(
                    "REST API로 주문 데이터를 수집합니다.",
                    "배치 작업으로 데이터를 집계하고 DB pipeline에 저장합니다.",
                ),
                {
                    "decision": "NOT_NEEDED",
                    "reason": "API와 배치 데이터 처리만 요구되어 화면 설계는 기본적으로 생략 가능합니다.",
                    "evidence_requirement_ids": [1, 2],
                    "candidate_screens": [],
                },
            ),
            (
                assessment_payload(
                    "모바일 사용자가 예약 가능한 시간을 조회합니다.",
                    "예약 내용을 확인하고 결제를 완료합니다.",
                ),
                {
                    "decision": "REQUIRED",
                    "reason": "모바일 예약과 결제 사용자 흐름이 핵심 기능으로 명시되어 UI 목업이 필요합니다.",
                    "evidence_requirement_ids": [1, 2],
                    "candidate_screens": ["예약 조회", "예약 확인", "결제"],
                },
            ),
        ]

        for payload, decision_payload in fixtures:
            with self.subTest(decision=decision_payload["decision"]):
                decision, parse_call = self._assess_with_mock(
                    payload,
                    UiMockupNecessityDecision.model_validate(decision_payload),
                )
                self.assertEqual(decision.decision, decision_payload["decision"])
                self.assertIs(
                    parse_call.kwargs["text_format"],
                    UiMockupNecessityDecision,
                )
                sent_context = json.loads(parse_call.kwargs["input"])
                self.assertEqual(
                    len(sent_context["confirmed_requirements"]),
                    len(payload["confirmed_requirements"]),
                )

    def test_assessment_endpoint_returns_project_decision(self):
        client = TestClient(app)
        with patch(
            "app.domains.planning_resources.ui_mockup_router.ui_mockup_service",
            StubUiMockupService(),
        ):
            response = client.post(
                "/api/v1/planning/ui-mockup/assess",
                json=request_payload(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "project_id": 17,
                "decision": "REQUIRED",
                "reason": "로그인과 대시보드 화면 상호작용이 명시되어 UI 목업이 필요합니다.",
                "evidence_requirement_ids": [1, 2],
                "candidate_screens": ["로그인", "프로젝트 대시보드"],
            },
        )

    def test_assessment_rejects_empty_confirmed_requirements_before_service(self):
        payload = request_payload()
        payload["confirmed_requirements"] = []
        service = Mock()
        client = TestClient(app)
        with patch(
            "app.domains.planning_resources.ui_mockup_router.ui_mockup_service",
            service,
        ):
            response = client.post(
                "/api/v1/planning/ui-mockup/assess",
                json=payload,
            )
        self.assertEqual(response.status_code, 422)
        service.assess.assert_not_called()

    def test_assessment_rejects_unknown_evidence_requirement_id(self):
        decision = UiMockupNecessityDecision(
            decision="RECOMMENDED",
            reason="운영자 확인 흐름이 있어 화면 검토가 권장됩니다.",
            evidence_requirement_ids=[999],
            candidate_screens=["운영 결과"],
        )
        with self.assertRaises(UiMockupLLMGenerationError):
            self._assess_with_mock(request_payload(), decision)

    def test_assessment_schema_rejects_invalid_decision_and_list_limits(self):
        base = {
            "decision": "REQUIRED",
            "reason": "사용자 화면이 명시되어 UI 목업이 필요합니다.",
            "evidence_requirement_ids": [1],
            "candidate_screens": ["대시보드"],
        }
        with self.assertRaises(ValidationError):
            UiMockupNecessityDecision.model_validate({**base, "decision": "MAYBE"})
        with self.assertRaises(ValidationError):
            UiMockupNecessityDecision.model_validate({
                **base,
                "evidence_requirement_ids": [1, 2, 3, 4, 5, 6],
            })
        with self.assertRaises(ValidationError):
            UiMockupNecessityDecision.model_validate({
                **base,
                "candidate_screens": [f"화면 {index}" for index in range(6)],
            })

    def test_not_needed_allows_empty_candidate_screens(self):
        decision = UiMockupNecessityDecision(
            decision="NOT_NEEDED",
            reason="API와 배치 처리만 요구되어 UI 목업을 생략할 수 있습니다.",
            evidence_requirement_ids=[1],
            candidate_screens=[],
        )
        self.assertEqual(decision.candidate_screens, [])

    def _assess_with_mock(
        self,
        payload: dict,
        parsed_decision: UiMockupNecessityDecision,
    ) -> tuple[UiMockupNecessityDecision, Mock]:
        parsed_response = Mock(output_parsed=parsed_decision)
        client = Mock()
        client.responses.parse.return_value = parsed_response
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch(
                "app.domains.planning_resources.ui_mockup_service.OpenAI",
                return_value=client,
            ),
        ):
            decision = UiMockupLLMService().assess(
                UiMockupGenerationRequest.model_validate(payload)
            )
        return decision, client.responses.parse.call_args


if __name__ == "__main__":
    unittest.main()
