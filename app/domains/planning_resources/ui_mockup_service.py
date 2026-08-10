"""OpenAI-backed structured UI mockup design service."""

from __future__ import annotations

import json
import os

from openai import OpenAI

from .ui_mockup import UiMockupGenerationRequest, UiMockupSpec


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

    @staticmethod
    def _instructions() -> str:
        return (
            "당신은 한국어 업무용 SaaS UX 설계자입니다. 확정 요구사항만 근거로 발표 가능한 "
            "대표 화면 1~3개를 설계하세요. 화면은 핵심 사용자 흐름을 보여줘야 하며 모든 문구는 "
            "짧은 한국어로 작성하세요. sections의 component_type은 schema가 허용한 값만 사용하고 "
            "화면마다 section은 최대 6개, primary_actions는 최대 3개로 제한하세요. 실제 데이터나 "
            "구현되지 않은 기능을 사실처럼 만들지 말고 요구사항에 없는 화면은 추가하지 마세요."
        )
