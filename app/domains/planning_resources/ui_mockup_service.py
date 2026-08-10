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
            "당신은 한국어 업무용 SaaS UX 설계자입니다. 확정 요구사항만 근거로 발표 가능한 "
            "대표 화면 1~3개를 설계하세요. 화면은 핵심 사용자 흐름을 보여줘야 하며 모든 문구는 "
            "짧은 한국어로 작성하세요. sections의 component_type은 schema가 허용한 값만 사용하고 "
            "화면마다 section은 최대 6개, primary_actions는 최대 3개로 제한하세요. 실제 데이터나 "
            "구현되지 않은 기능을 사실처럼 만들지 말고 요구사항에 없는 화면은 추가하지 마세요."
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
