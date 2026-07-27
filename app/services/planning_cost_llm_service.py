from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator

from app.schemas.planning_cost import PotentialCostType


load_dotenv()


class GeneratedPotentialCost(BaseModel):
    cost_type: PotentialCostType
    cost_name: str
    reason: str

    @model_validator(mode="after")
    def normalize_cost(self) -> "GeneratedPotentialCost":
        self.cost_name = self.cost_name.strip()
        self.reason = self.reason.strip()
        if not self.cost_name or not self.reason:
            raise ValueError("추가 비용명과 판단 이유가 필요합니다.")
        return self


class GeneratedCostAnalysis(BaseModel):
    potential_additional_costs: list[GeneratedPotentialCost] = Field(
        default_factory=list,
        max_length=20,
    )


class CostLLMConfigurationError(RuntimeError):
    pass


class CostLLMGenerationError(RuntimeError):
    pass


class PlanningCostLLMService:
    def generate(self, context: dict) -> GeneratedCostAnalysis:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise CostLLMConfigurationError(
                "OPENAI_API_KEY가 설정되지 않았습니다."
            )

        try:
            client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
            return self._request(client, context)
        except CostLLMGenerationError:
            raise
        except Exception as exc:
            raise CostLLMGenerationError(
                "OpenAI 추가 비용 항목 분석 요청에 실패했습니다."
            ) from exc

    def _request(
        self,
        client: OpenAI,
        context: dict,
    ) -> GeneratedCostAnalysis:
        try:
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=GeneratedCostAnalysis,
                store=False,
            )
        except Exception as exc:
            raise CostLLMGenerationError(
                "OpenAI가 프로젝트의 추가 비용 항목을 분석하지 못했습니다."
            ) from exc

        if response.output_parsed is None:
            raise CostLLMGenerationError(
                "OpenAI가 구조화된 추가 비용 분석 결과를 반환하지 않았습니다."
            )
        return response.output_parsed

    def _instructions(self) -> str:
        return (
            "당신은 IT 개발 프로젝트의 초기 견적 검토 전문가입니다. 프로젝트명과 WBS를 "
            "검토하여 기본 계산에 포함되지 않은 추가 비용 후보만 반환하세요. 인건비, 기본 "
            "서버비, 일반 개발 도구 라이선스비, 기본 AI API 비용은 이미 Python으로 계산되므로 "
            "반환하지 마세요. 데이터베이스, 저장소, 별도 외부 API, 특수 라이선스, 모니터링, "
            "보안 솔루션, 하드웨어, 외주, 데이터 구매 등 WBS에서 합리적으로 근거를 찾을 수 "
            "있는 항목만 선택하세요. 금액, 단가, 수량을 추정하거나 생성하지 마세요. cost_name은 "
            "짧고 구체적인 한국어 이름으로, reason은 해당 WBS에 근거한 간결한 한국어 한 "
            "문장으로 작성하세요. 근거가 없으면 빈 목록을 반환하세요."
        )
