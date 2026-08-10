from __future__ import annotations

import base64
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageFont
from pydantic import ValidationError

from app.domains.planning_resources.ui_mockup import (
    UiMockupGenerationRequest,
    UiMockupSpec,
    render_ui_mockup,
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


if __name__ == "__main__":
    unittest.main()
