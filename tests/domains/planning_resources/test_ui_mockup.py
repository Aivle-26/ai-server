from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from app.domains.planning_resources.ui_mockup import (
    UiMockupGenerationRequest,
    UiMockupNecessityDecision,
    UiMockupSpec,
    _fit_text,
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
            "platform": "WEB",
            "screens": [
                {
                    "screen_name": "프로젝트 대시보드",
                    "purpose": "진행 상태와 주요 업무를 요약합니다.",
                    "page_type": "DASHBOARD",
                    "navigation_type": "SIDEBAR",
                    "layout_type": "GRID",
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
                    "page_type": "LIST",
                    "navigation_type": "TABS",
                    "layout_type": "MASTER_DETAIL",
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


def mobile_booking_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "동네 체험 예약 앱",
            "design_summary": "모바일 사용자가 주변 체험을 찾고 예약과 결제를 완료하는 흐름",
            "platform": "MOBILE",
            "screens": [
                {
                    "screen_name": "홈과 예약 검색",
                    "purpose": "지역과 날짜를 선택해 예약 가능한 체험을 찾습니다.",
                    "page_type": "BOOKING",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "FORM_FLOW",
                    "navigation": ["홈", "지도", "채팅", "마이"],
                    "sections": [
                        {
                            "title": "체험 검색",
                            "component_type": "form",
                            "items": ["지역 검색", "날짜 선택", "예약 가능 시간"],
                        },
                        {
                            "title": "추천 체험",
                            "component_type": "card",
                            "items": ["도자기 체험", "쿠킹 클래스"],
                        },
                    ],
                    "primary_actions": ["예약 시간 선택"],
                },
                {
                    "screen_name": "지도 탐색",
                    "purpose": "현재 위치 주변의 체험 장소를 지도에서 확인합니다.",
                    "page_type": "MAP",
                    "navigation_type": "BOTTOM_NAV",
                    "layout_type": "MASTER_DETAIL",
                    "navigation": ["홈", "지도", "채팅", "마이"],
                    "sections": [
                        {
                            "title": "주변 체험 장소",
                            "component_type": "list",
                            "items": ["거리순 결과", "예약 가능 장소"],
                        }
                    ],
                    "primary_actions": ["장소 보기"],
                },
                {
                    "screen_name": "예약 확인과 결제",
                    "purpose": "선택한 일정과 결제 정보를 확인하고 예약을 확정합니다.",
                    "page_type": "DETAIL",
                    "navigation_type": "NONE",
                    "layout_type": "FORM_FLOW",
                    "navigation": [],
                    "sections": [
                        {
                            "title": "예약 정보",
                            "component_type": "card",
                            "items": ["선택한 체험", "예약 날짜와 시간", "결제 수단"],
                        }
                    ],
                    "primary_actions": ["예약 확정"],
                },
            ],
        }
    )


def ecommerce_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "로컬 브랜드 온라인 쇼핑몰",
            "design_summary": "상품 탐색에서 상세 확인과 주문으로 이어지는 웹 쇼핑 흐름",
            "platform": "WEB",
            "screens": [
                {
                    "screen_name": "상품 탐색",
                    "purpose": "상품을 검색하고 카테고리별로 비교합니다.",
                    "page_type": "ECOMMERCE",
                    "navigation_type": "TOP_NAV",
                    "layout_type": "GRID",
                    "navigation": ["신상품", "카테고리", "장바구니"],
                    "sections": [
                        {
                            "title": "상품 검색",
                            "component_type": "form",
                            "items": ["리빙", "패션", "푸드", "지역 브랜드 상품"],
                        }
                    ],
                    "primary_actions": ["상품 보기"],
                },
                {
                    "screen_name": "상품 상세",
                    "purpose": "상품 정보와 배송 조건을 확인하고 장바구니에 담습니다.",
                    "page_type": "DETAIL",
                    "navigation_type": "TOP_NAV",
                    "layout_type": "TWO_COLUMN",
                    "navigation": ["상품", "리뷰", "배송"],
                    "sections": [
                        {
                            "title": "상품 정보",
                            "component_type": "card",
                            "items": ["상품 설명", "옵션 선택", "배송 안내"],
                        }
                    ],
                    "primary_actions": ["장바구니 담기"],
                },
            ],
        }
    )


def api_etl_spec() -> UiMockupSpec:
    return UiMockupSpec.model_validate(
        {
            "project_title": "주문 데이터 ETL API",
            "design_summary": "요구사항에 명시된 데이터 입력과 변환 범위만 설명하는 화면",
            "platform": "WEB",
            "screens": [
                {
                    "screen_name": "처리 범위 명세",
                    "purpose": "API 입력과 ETL 변환 규칙을 읽기 전용으로 확인합니다.",
                    "page_type": "DETAIL",
                    "navigation_type": "NONE",
                    "layout_type": "FULL_WIDTH",
                    "navigation": [],
                    "sections": [
                        {
                            "title": "API 입력",
                            "component_type": "list",
                            "items": ["주문 데이터 수집", "입력 형식 검증"],
                        },
                        {
                            "title": "ETL 변환",
                            "component_type": "list",
                            "items": ["필드 정규화", "저장 대상 전달"],
                        },
                    ],
                    "primary_actions": [],
                }
            ],
        }
    )


def generation_payload(
    project_title: str,
    project_description: str,
    *requirements: str,
) -> dict:
    return {
        "project_id": 71,
        "project_title": project_title,
        "project_description": project_description,
        "confirmed_requirements": [
            {
                "requirement_id": index,
                "title": f"확정 요구사항 {index}",
                "description": description,
                "category": "FUNCTIONAL",
                "priority": "HIGH",
            }
            for index, description in enumerate(requirements, start=1)
        ],
    }


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

    def test_mobile_schema_rejects_sidebar_navigation(self):
        payload = mobile_booking_spec().model_dump()
        payload["screens"][0]["navigation_type"] = "SIDEBAR"
        with self.assertRaises(ValidationError):
            UiMockupSpec.model_validate(payload)

    def test_generation_fixtures_preserve_domain_layout_semantics(self):
        fixtures = [
            (
                generation_payload(
                    "동네 체험 예약 앱",
                    "모바일 사용자를 위한 예약 서비스",
                    "모바일 사용자는 회원가입과 로그인을 할 수 있습니다.",
                    "지역과 날짜로 체험을 검색합니다.",
                    "예약 가능한 시간을 선택합니다.",
                    "결제를 완료하고 예약을 확인합니다.",
                    "지도에서 주변 장소를 찾습니다.",
                    "호스트와 채팅하고 리뷰를 작성합니다.",
                    "마이페이지에서 예약 내역을 확인합니다.",
                ),
                mobile_booking_spec(),
                "MOBILE",
                {"BOOKING", "MAP", "DETAIL"},
            ),
            (
                generation_payload(
                    "로컬 브랜드 온라인 쇼핑몰",
                    "상품 판매를 위한 웹 쇼핑몰",
                    "상품 목록을 카테고리와 검색으로 탐색합니다.",
                    "상품 상세와 리뷰 및 배송 조건을 확인합니다.",
                    "장바구니에 담고 주문을 진행합니다.",
                ),
                ecommerce_spec(),
                "WEB",
                {"ECOMMERCE", "DETAIL"},
            ),
            (
                request_payload(),
                mockup_spec(),
                "WEB",
                {"DASHBOARD", "LIST"},
            ),
            (
                generation_payload(
                    "주문 데이터 ETL API",
                    "화면이 없는 API와 배치 데이터 파이프라인",
                    "REST API로 주문 데이터를 수집합니다.",
                    "ETL 배치가 필드를 정규화해 저장 대상으로 전달합니다.",
                ),
                api_etl_spec(),
                "WEB",
                {"DETAIL"},
            ),
        ]

        for payload, parsed_spec, platform, page_types in fixtures:
            with self.subTest(project=payload["project_title"]):
                generated, parse_call = self._generate_with_mock(payload, parsed_spec)
                self.assertEqual(generated.platform, platform)
                self.assertEqual(
                    {screen.page_type for screen in generated.screens},
                    page_types,
                )
                sent_context = json.loads(parse_call.kwargs["input"])
                self.assertEqual(
                    sent_context["confirmed_requirements"][0]["description"],
                    payload["confirmed_requirements"][0]["description"],
                )
                instructions = parse_call.kwargs["instructions"]
                self.assertIn("confirmed_requirements", instructions)
                self.assertIn("Pmate AI", instructions)
                self.assertIn("근거가 없는 실제 수치", instructions)
                self.assertNotIn("한국어 업무용 SaaS UX 설계자", instructions)

        mobile = fixtures[0][1]
        self.assertTrue(all(screen.page_type != "DASHBOARD" for screen in mobile.screens))
        self.assertTrue(all(screen.navigation_type != "SIDEBAR" for screen in mobile.screens))
        forced_api = fixtures[3][1]
        self.assertTrue(all(screen.page_type != "DASHBOARD" for screen in forced_api.screens))
        self.assertTrue(all(screen.navigation_type == "NONE" for screen in forced_api.screens))

    def test_domain_renderers_are_semantically_and_visually_distinct(self):
        specs = [mobile_booking_spec(), ecommerce_spec(), mockup_spec()]
        with patch(
            "app.domains.planning_resources.ui_mockup._resolve_font_path",
            return_value=usable_font_path(),
        ):
            rendered = [render_ui_mockup(spec) for spec in specs]

        hashes = {hashlib.sha256(item.content).hexdigest() for item in rendered}
        self.assertEqual(len(hashes), 3)
        for item in rendered:
            self.assertTrue(item.content.startswith(b"\xff\xd8\xff"))
            image = Image.open(BytesIO(item.content))
            self.assertEqual(image.size, (1920, 1080))

        mobile_image = Image.open(BytesIO(rendered[0].content)).convert("RGB")
        dark_phone_pixels = sum(
            1
            for red, green, blue in mobile_image.getdata()
            if red < 45 and green < 60 and blue < 85
        )
        self.assertGreater(dark_phone_pixels, 8_000)
        self.assertEqual(specs[0].platform, "MOBILE")
        self.assertEqual(specs[0].screens[0].page_type, "BOOKING")
        self.assertEqual(specs[1].screens[0].page_type, "ECOMMERCE")
        self.assertEqual(specs[2].screens[0].page_type, "DASHBOARD")
        self.assertEqual(specs[2].screens[0].navigation_type, "SIDEBAR")

    def test_long_korean_text_is_fitted_inside_renderer_bounds(self):
        image = Image.new("RGB", (400, 100), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(usable_font_path()), 18)
        fitted = _fit_text(
            draw,
            "모바일 예약 서비스의 매우 긴 화면 제목과 사용자 흐름 설명이 부모 영역을 넘지 않아야 합니다",
            font,
            180,
        )
        left, _, right, _ = draw.textbbox((0, 0), fitted, font=font)
        self.assertLessEqual(right - left, 180)
        self.assertTrue(fitted.endswith("..."))

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

    def _generate_with_mock(
        self,
        payload: dict,
        parsed_spec: UiMockupSpec,
    ) -> tuple[UiMockupSpec, Mock]:
        parsed_response = Mock(output_parsed=parsed_spec)
        client = Mock()
        client.responses.parse.return_value = parsed_response
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch(
                "app.domains.planning_resources.ui_mockup_service.OpenAI",
                return_value=client,
            ),
        ):
            generated = UiMockupLLMService().generate(
                UiMockupGenerationRequest.model_validate(payload)
            )
        return generated, client.responses.parse.call_args


if __name__ == "__main__":
    unittest.main()
