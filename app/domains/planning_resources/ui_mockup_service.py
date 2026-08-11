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
        context = {
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
        return response.output_parsed

    def assess(
        self,
        request: UiMockupGenerationRequest,
    ) -> UiMockupNecessityDecision:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise UiMockupLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")
        context = {
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
    def _instructions() -> str:
        return (
            "당신은 확정 요구사항을 분석해 프로젝트 도메인과 사용자 흐름에 맞는 제품 UI를 "
            "설계하는 UX architect입니다. 판단 근거의 우선순위는 confirmed_requirements, "
            "project_description, project_title 순서입니다. 대표 화면 1~3개와 platform, page_type, "
            "navigation_type, layout_type을 선택하세요. 모바일 사용자나 모바일 앱이 명시되면 "
            "MOBILE을 선택하고 SIDEBAR를 사용하지 마세요. 예약 서비스는 검색-일정 선택-예약 확인, "
            "쇼핑몰은 상품 목록-상세-장바구니/주문, 커뮤니티는 피드-상세-작성처럼 요구사항의 "
            "실제 사용자 흐름을 우선하세요. 프로젝트 관리 제품일 때만 dashboard/sidebar를 사용하세요. "
            "REST API, batch, ETL처럼 화면이 필요하지 않은 프로젝트에서 생성이 강제되더라도 "
            "관리자 대시보드를 발명하지 말고 요구사항에 표현된 정보 범위만 시각화하세요. "
            "모든 문구는 짧은 한국어로 작성하고 sections의 component_type은 schema가 허용한 값만 "
            "사용하세요. Pmate AI, 프로젝트/요구사항/일정/리스크 메뉴, 주간 보고서처럼 입력에 없는 "
            "우리 서비스의 브랜드나 기능을 넣지 마세요. 진행률, D-day, 건수, 매출처럼 요구사항에 "
            "근거가 없는 실제 수치를 만들지 마세요. 화면마다 section은 최대 6개, primary_actions는 "
            "최대 3개로 제한하고 요구사항에 없는 화면이나 기능은 추가하지 마세요."
        )

    @staticmethod
    def _assessment_instructions() -> str:
        return (
            "당신은 프로젝트 산출물 검토자입니다. 확정 요구사항만 근거로 UI 목업 필요성을 "
            "REQUIRED, RECOMMENDED, NOT_NEEDED 중 하나로 판단하세요. project_description은 "
            "보조 정보이며 confirmed_requirements가 가장 강한 근거입니다. 로그인, 대시보드, "
            "목록, 상세, 입력 폼, 관리 화면, 모바일 사용자 흐름처럼 실제 화면 interaction이 "
            "명시되면 REQUIRED입니다. 화면이 명시되지 않아도 운영자나 사용자가 처리 결과를 "
            "확인하는 흐름이 있으면 RECOMMENDED입니다. REST API, batch, ETL, data pipeline, "
            "infrastructure, model serving, pure library만 요구되면 NOT_NEEDED입니다. 기술명이나 "
            "프로젝트명만으로 UI를 추측하지 마세요. evidence_requirement_ids에는 입력된 confirmed "
            "requirement ID만 최대 5개 사용하세요. REQUIRED 또는 RECOMMENDED이면 요구사항에서 "
            "직접 예상 가능한 대표 화면만 최대 5개 제시하세요. reason은 PM이 이해할 수 있는 "
            "한국어 최대 두 문장으로 작성하고, 이 판단이 생성 API를 차단하지는 않습니다."
        )
