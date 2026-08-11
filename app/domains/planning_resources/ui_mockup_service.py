"""OpenAI-backed structured UI mockup design service."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from .ui_mockup import (
    UiMockupGenerationRequest,
    UiMockupNecessityDecision,
    UiMockupSpec,
)


class UiMockupLLMConfigurationError(RuntimeError):
    pass


class UiMockupLLMGenerationError(RuntimeError):
    pass


class UiMockupLLMService:
    def generate(self, request: UiMockupGenerationRequest) -> UiMockupSpec:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise UiMockupLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")
        context = self._context(request)
        try:
            client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=UiMockupSpec,
                store=False,
            )
        except Exception as exc:
            raise UiMockupLLMGenerationError("UI 목업 화면 설계 생성에 실패했습니다.") from exc
        if response.output_parsed is None:
            raise UiMockupLLMGenerationError("구조화된 UI 목업 설계가 반환되지 않았습니다.")
        return self._validate_generated_spec(request, response.output_parsed)

    def assess(
        self,
        request: UiMockupGenerationRequest,
    ) -> UiMockupNecessityDecision:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise UiMockupLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")
        context = self._context(request)
        try:
            client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._assessment_instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=UiMockupNecessityDecision,
                store=False,
            )
        except Exception as exc:
            raise UiMockupLLMGenerationError(
                "UI 목업 필요성 판단에 실패했습니다."
            ) from exc
        if response.output_parsed is None:
            raise UiMockupLLMGenerationError(
                "구조화된 UI 목업 필요성 판단이 반환되지 않았습니다."
            )

        decision = response.output_parsed
        allowed_ids = {
            requirement.requirement_id
            for requirement in request.confirmed_requirements
        }
        unknown_ids = set(decision.evidence_requirement_ids) - allowed_ids
        if unknown_ids:
            raise UiMockupLLMGenerationError(
                "UI 목업 필요성 판단에 입력되지 않은 요구사항 ID가 포함되었습니다."
            )
        return decision

    @staticmethod
    def _context(request: UiMockupGenerationRequest) -> dict:
        return {
            "project_title": request.project_title,
            "project_description": request.project_description,
            "confirmed_requirements": [
                {
                    "id": requirement.requirement_id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "category": requirement.category,
                    "priority": requirement.priority,
                }
                for requirement in request.confirmed_requirements
            ],
        }

    @staticmethod
    def _validate_generated_spec(
        request: UiMockupGenerationRequest,
        spec: UiMockupSpec,
    ) -> UiMockupSpec:
        allowed_ids = {
            requirement.requirement_id
            for requirement in request.confirmed_requirements
        }
        evidence_ids = {
            requirement_id
            for screen in spec.screens
            for requirement_id in screen.evidence_requirement_ids
        }
        if evidence_ids - allowed_ids:
            raise UiMockupLLMGenerationError(
                "UI 목업 화면에 입력되지 않은 요구사항 ID가 포함되었습니다."
            )
        return spec

    @staticmethod
    def _screen_selection_principles() -> str:
        return (
            "confirmed_requirements를 유일한 기능 source of truth로 사용하고 프로젝트명만으로 "
            "기능을 추측하지 마세요. 화면을 바로 고르지 말고 먼저 요구사항에서 actor를 분리한 뒤 "
            "가장 중요한 primary actor, 그 actor의 핵심 목표, 목표를 완료하는 하나의 end-to-end "
            "journey를 순서대로 선택하세요. priority가 HIGH, MUST 또는 필수인 요구사항, 명시적인 "
            "화면 interaction, 검색-예약-결제나 탐색-구매 같은 핵심 거래 흐름, 여러 요구사항이 "
            "연결되는 단계를 우선하세요. 대표 화면은 한 primary actor의 journey 순서를 따라야 하며 "
            "CUSTOMER, PARTNER, ADMIN 화면을 이유 없이 섞지 마세요. 화면이 3개를 넘는 journey는 "
            "서비스 상세+예약 옵션, 결제+최종 확인처럼 인접 단계를 한 화면에 합쳐 핵심 HIGH/MUST "
            "요구사항을 최대한 커버하세요."
        )

    @classmethod
    def _instructions(cls) -> str:
        return (
            "당신은 확정 요구사항을 분석해 프로젝트 도메인과 사용자 흐름에 맞는 제품 UI를 "
            "설계하는 UX architect입니다. "
            + cls._screen_selection_principles()
            + " UiMockupSpec의 primary_actor와 journey_summary를 먼저 확정하고 screens는 journey_step "
            "1부터 끊김 없이 배열하세요. 각 screen.actor는 primary_actor와 같아야 하고, "
            "evidence_requirement_ids에는 그 화면의 근거가 된 입력 requirement ID를 1~6개 넣으세요. "
            "입력에 없는 ID는 절대 만들지 마세요. 화면명은 지역 서비스 검색 결과, 서비스 상세 및 "
            "예약, 결제 및 예약 확정처럼 도메인과 목표가 드러나야 하며 메인 화면, 목록 화면, 상세 "
            "화면 같은 generic 이름을 사용하지 마세요. 대표 화면 1~3개와 platform, page_type, "
            "navigation_type, layout_type을 선택하세요. 모바일 사용자나 모바일 앱이 명시되면 "
            "MOBILE을 선택하고 SIDEBAR를 사용하지 마세요. 예약 서비스는 검색-일정 선택-예약 확인, "
            "쇼핑몰은 상품 목록-상세-장바구니/주문, 커뮤니티는 피드-상세-작성처럼 요구사항의 "
            "실제 사용자 흐름을 우선하세요. 프로젝트 관리 제품일 때만 dashboard/sidebar를 사용하세요. "
            "REST API, batch, ETL처럼 화면이 필요하지 않은 프로젝트에서 생성이 강제되더라도 "
            "관리자 대시보드를 발명하지 말고 요구사항에 표현된 정보 범위만 시각화하세요. "
            "sections에는 근거 요구사항의 실제 interaction과 정보를 넣으세요. 검색창은 search_bar, "
            "필터는 filter_chips, 카테고리는 category_grid, 서비스 결과는 service_card, 지도는 "
            "map_preview, 날짜는 date_picker, 예약 시간은 time_slots, 옵션은 option_selector, 가격과 "
            "쿠폰은 price_summary, 결제 수단은 payment_methods, 리뷰는 review_summary를 사용하세요. "
            "필요하지 않은 semantic component를 억지로 넣지 말고 기존 component_type으로 충분하면 "
            "재사용하세요. 모든 문구는 짧은 한국어로 작성하세요. Pmate AI, 프로젝트/요구사항/일정/리스크 "
            "메뉴, 주간 보고서처럼 입력에 없는 "
            "우리 서비스의 브랜드나 기능을 넣지 마세요. 진행률, D-day, 건수, 매출처럼 요구사항에 "
            "근거가 없는 실제 수치를 만들지 마세요. 화면마다 section은 최대 6개, primary_actions는 "
            "최대 3개로 제한하고 요구사항에 없는 화면이나 기능은 추가하지 마세요."
        )

    @classmethod
    def _assessment_instructions(cls) -> str:
        return (
            "당신은 프로젝트 산출물 검토자입니다. 확정 요구사항만 근거로 UI 목업 필요성을 "
            "REQUIRED, RECOMMENDED, NOT_NEEDED 중 하나로 판단하세요. project_description은 "
            "보조 정보이며 confirmed_requirements가 가장 강한 근거입니다. "
            + cls._screen_selection_principles()
            + " 로그인, 대시보드, "
            "목록, 상세, 입력 폼, 관리 화면, 모바일 사용자 흐름처럼 실제 화면 interaction이 "
            "명시되면 REQUIRED입니다. 화면이 명시되지 않아도 운영자나 사용자가 처리 결과를 "
            "확인하는 흐름이 있으면 RECOMMENDED입니다. REST API, batch, ETL, data pipeline, "
            "infrastructure, model serving, pure library만 요구되면 NOT_NEEDED입니다. 기술명이나 "
            "프로젝트명만으로 UI를 추측하지 마세요. evidence_requirement_ids에는 입력된 confirmed "
            "requirement ID만 최대 5개 사용하세요. REQUIRED 또는 RECOMMENDED이면 요구사항에서 "
            "직접 예상 가능한 대표 화면만 최대 5개 제시하고, candidate_screens도 선택한 primary "
            "actor의 같은 journey 순서와 도메인별 화면명을 따르세요. reason은 PM이 이해할 수 있는 "
            "한국어 최대 두 문장으로 작성하고, 이 판단이 생성 API를 차단하지는 않습니다."
        )
