"""WBS TASK별 역할·기술·공수를 추정하는 LLM 서비스."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator


load_dotenv()


class GeneratedRequiredSkill(BaseModel):
    skill_code: str
    minimum_proficiency_level: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def normalize_skill(self) -> "GeneratedRequiredSkill":
        self.skill_code = self.skill_code.strip().upper()
        if not self.skill_code:
            raise ValueError("기술 코드는 비어 있을 수 없습니다.")
        return self


class GeneratedTaskResourceEstimate(BaseModel):
    wbs_id: int = Field(gt=0)
    required_role_code: str
    required_skills: list[GeneratedRequiredSkill] = Field(
        default_factory=list,
        max_length=20,
    )
    estimated_person_days: float = Field(ge=0.5, le=2_000)
    estimation_reason: str

    @model_validator(mode="after")
    def normalize_estimate(self) -> "GeneratedTaskResourceEstimate":
        self.required_role_code = self.required_role_code.strip().upper()
        self.estimation_reason = self.estimation_reason.strip()
        if not self.required_role_code or not self.estimation_reason:
            raise ValueError("필요 역할과 공수 추정 근거가 필요합니다.")
        return self


class GeneratedResourcePlan(BaseModel):
    task_estimates: list[GeneratedTaskResourceEstimate] = Field(
        min_length=1,
        max_length=30,
    )


class ResourceLLMConfigurationError(RuntimeError):
    pass


class ResourceLLMGenerationError(RuntimeError):
    pass


class PlanningResourceLLMService:
    def generate(self, contexts: list[dict]) -> list[GeneratedResourcePlan]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ResourceLLMConfigurationError(
                "OPENAI_API_KEY가 설정되지 않았습니다."
            )

        max_workers = min(3, len(contexts))
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                return list(executor.map(
                    lambda context: self._generate_one(api_key, context),
                    contexts,
                ))
        except ResourceLLMGenerationError:
            raise
        except Exception as exc:
            raise ResourceLLMGenerationError(
                "OpenAI 인력·공수 추정 요청에 실패했습니다."
            ) from exc

    def _generate_one(
        self,
        api_key: str,
        context: dict,
    ) -> GeneratedResourcePlan:
        client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
        return self._request_one(client, context)

    def _request_one(self, client: OpenAI, context: dict) -> GeneratedResourcePlan:
        try:
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=GeneratedResourcePlan,
                store=False,
            )
        except Exception as exc:
            raise ResourceLLMGenerationError(
                "OpenAI가 WBS 작업의 필요 인력과 공수를 추정하지 못했습니다."
            ) from exc

        if response.output_parsed is None:
            raise ResourceLLMGenerationError(
                "OpenAI가 구조화된 인력·공수 추정 결과를 반환하지 않았습니다."
            )
        return response.output_parsed

    def _instructions(self) -> str:
        return (
            "당신은 IT 개발 프로젝트의 공수 산정 전문가입니다. 입력에 포함된 모든 TASK를 "
            "정확히 한 번씩 반환하세요. 각 TASK의 설명을 바탕으로 가장 적합한 필요 역할 한 개, "
            "핵심 필요 기술과 최소 숙련도, 예상 인일을 추정하세요. required_role_code와 "
            "skill_code는 입력의 allowed_role_codes와 allowed_skill_codes에 존재하는 값만 "
            "사용하세요. estimated_person_days는 한 사람이 해당 작업을 수행하는 데 필요한 총 "
            "업무량이며, TASK의 달력상 기간이나 참여자의 현재 가용시간에 맞춰 줄이지 마세요. "
            "담당자 ID, MM, 실제 배정 시간, 시작일과 종료일은 생성하지 마세요. 공수 추정 근거는 "
            "간결한 한국어 한 문장으로 작성하세요."
        )
