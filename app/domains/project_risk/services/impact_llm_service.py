from __future__ import annotations

import json
import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv()


ImpactType = Literal["DIRECT", "INDIRECT", "NONE"]


class LLMAffectedTask(BaseModel):
    """LLM이 식별한 영향 태스크 한 건."""

    task_id: int
    impact_type: ImpactType
    additional_work_days: int = Field(default=0, ge=0)
    reason: str


class GeneratedImpactAnalysis(BaseModel):
    """변경 설명 → 영향 분석 구조화 결과."""

    affected_tasks: list[LLMAffectedTask] = Field(default_factory=list)
    scope_changed: bool = False
    database_changed: bool = False
    api_changed: bool = False
    ui_changed: bool = False
    summary: str = ""


class ImpactLLMConfigurationError(RuntimeError):
    pass


class ImpactLLMGenerationError(RuntimeError):
    pass


class ImpactAnalysisLLMService:
    """변경 제목·설명 + 확정 WBS 목록을 받아 영향 태스크와 추가 공수를 산출한다.

    planning_wbs.PlanningWBSLLMService와 동일한 방식(OpenAI responses.parse +
    Pydantic 구조화 출력)을 재활용한다.
    """

    def analyze(self, context: dict) -> GeneratedImpactAnalysis:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ImpactLLMConfigurationError(
                "OPENAI_API_KEY가 설정되지 않았습니다."
            )

        client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
        try:
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=GeneratedImpactAnalysis,
                store=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ImpactLLMGenerationError(
                "OpenAI가 영향도 분석을 생성하지 못했습니다."
            ) from exc

        if response.output_parsed is None:
            raise ImpactLLMGenerationError(
                "OpenAI가 구조화된 영향도 결과를 반환하지 않았습니다."
            )
        return response.output_parsed

    def _instructions(self) -> str:
        return (
            "당신은 IT 개발 프로젝트의 요구사항 변경 영향도를 평가하는 전문가입니다. "
            "입력으로 변경 제목(change_title), 변경 설명(change_description), 확정된 "
            "WBS 태스크 목록(wbs_tasks)이 주어집니다. "
            "변경 설명을 WBS 태스크와 대조하여 실제로 영향을 받는 태스크만 골라내세요. "
            "각 영향 태스크에 대해 impact_type(DIRECT=직접 수정 필요, "
            "INDIRECT=간접 영향/회귀 확인 필요, NONE=영향 없음)과 추가 작업일"
            "(additional_work_days, 정수 일수)을 산정하고, 판단 근거(reason)를 "
            "간결한 한국어로 작성하세요. "
            "반드시 입력 wbs_tasks에 실제로 존재하는 task_id만 사용하세요. "
            "존재하지 않는 id를 지어내지 마세요. 영향이 없는 태스크는 목록에 넣지 마세요. "
            "변경 설명에서 프로젝트 범위 변경(scope_changed), 데이터베이스 변경"
            "(database_changed), API 변경(api_changed), 화면/UI 변경(ui_changed) "
            "필요 여부를 각각 boolean으로 추론하세요. "
            "summary에는 변경이 프로젝트에 미치는 영향을 2~3문장 한국어로 요약하세요."
        )
