"""WBS TASK 기간을 구조화된 형태로 추정하는 LLM 서비스."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv()


class GeneratedTaskScheduleEstimate(BaseModel):
    wbs_id: int = Field(gt=0)
    optimistic_days: int = Field(ge=1, le=365)
    most_likely_days: int = Field(ge=1, le=365)
    pessimistic_days: int = Field(ge=1, le=365)
    predecessor_wbs_ids: list[int] = Field(default_factory=list, max_length=50)
    milestone: bool = False
    buffer_days: int = Field(default=0, ge=0, le=365)


class GeneratedSchedulePlan(BaseModel):
    task_estimates: list[GeneratedTaskScheduleEstimate] = Field(
        min_length=1,
        max_length=200,
    )


class ScheduleLLMConfigurationError(RuntimeError):
    pass


class ScheduleLLMGenerationError(RuntimeError):
    pass


class PlanningScheduleLLMService:
    def generate(self, context: dict) -> GeneratedSchedulePlan:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ScheduleLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")

        try:
            client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=GeneratedSchedulePlan,
                store=False,
            )
        except Exception as exc:
            raise ScheduleLLMGenerationError(
                "OpenAI가 WBS 작업 기간을 추정하지 못했습니다."
            ) from exc

        if response.output_parsed is None:
            raise ScheduleLLMGenerationError(
                "OpenAI가 구조화된 일정 추정 결과를 반환하지 않았습니다."
            )
        return response.output_parsed

    def _instructions(self) -> str:
        return (
            "당신은 IT 개발 프로젝트의 WBS 일정 추정 전문가입니다. "
            "입력에 있는 모든 TASK를 정확히 한 번씩 반환하세요. 각 TASK에 낙관 기간, "
            "가장 가능성 높은 기간, 비관 기간을 정수 영업일로 추정하세요. 기간은 반드시 "
            "optimistic_days <= most_likely_days <= pessimistic_days 관계를 만족해야 합니다. "
            "predecessor_wbs_ids에는 입력에 존재하는 TASK 중 현재 TASK보다 먼저 완료되어야 하는 "
            "직접 선행 TASK만 넣으세요. 자기 자신, 존재하지 않는 ID, 순환 관계를 만들지 마세요. "
            "WBS 코드와 단계 순서를 존중하되 독립 수행이 가능한 작업은 불필요하게 직렬화하지 마세요. "
            "담당자, 실제 날짜, 진척률과 비용은 생성하지 마세요."
        )
