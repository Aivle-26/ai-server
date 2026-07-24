from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from app.schemas.planning_document import ArtifactType


load_dotenv()


class GeneratedWBSTask(BaseModel):
    name: str
    description: str
    mapped_requirement_ids: list[int] = Field(default_factory=list)
    related_artifact_types: list[ArtifactType] = Field(default_factory=list)
    completion_criteria: list[str] = Field(min_length=1, max_length=20)


class GeneratedWBSWorkPackage(BaseModel):
    name: str
    description: str
    completion_criteria: list[str] = Field(min_length=1, max_length=20)
    tasks: list[GeneratedWBSTask] = Field(min_length=1, max_length=100)


class GeneratedWBSPhase(BaseModel):
    phase_name: str
    description: str
    completion_criteria: list[str] = Field(min_length=1, max_length=20)
    work_packages: list[GeneratedWBSWorkPackage] = Field(default_factory=list, max_length=50)


class GeneratedWBSPlan(BaseModel):
    phases: list[GeneratedWBSPhase] = Field(min_length=1, max_length=20)


class WBSLLMConfigurationError(RuntimeError):
    pass


class WBSLLMGenerationError(RuntimeError):
    pass


class PlanningWBSLLMService:
    def generate(self, contexts: list[dict]) -> list[GeneratedWBSPlan]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise WBSLLMConfigurationError("OPENAI_API_KEY가 설정되지 않았습니다.")

        max_workers = min(3, len(contexts))
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                return list(executor.map(
                    lambda context: self._generate_one(api_key, context),
                    contexts,
                ))
        except WBSLLMGenerationError:
            raise
        except Exception as exc:
            raise WBSLLMGenerationError("OpenAI WBS 생성 요청에 실패했습니다.") from exc

    def _generate_one(self, api_key: str, context: dict) -> GeneratedWBSPlan:
        client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
        return self._request_one(client, context)

    def _request_one(self, client: OpenAI, context: dict) -> GeneratedWBSPlan:
        try:
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=GeneratedWBSPlan,
                store=False,
            )
        except Exception as exc:
            raise WBSLLMGenerationError("OpenAI가 WBS 구조를 생성하지 못했습니다.") from exc

        if response.output_parsed is None:
            raise WBSLLMGenerationError("OpenAI가 구조화된 WBS 결과를 반환하지 않았습니다.")
        return response.output_parsed

    def _instructions(self) -> str:
        return (
            "당신은 IT 개발 프로젝트의 WBS 작업분해구조를 설계하는 전문가입니다. "
            "입력의 methodology 순서를 그대로 사용하고, 각 단계에 WORK_PACKAGE와 실제 수행 가능한 "
            "TASK를 만드세요. 일정, 날짜, 기간, 작업시간, 선행 작업, 담당자, 담당 역할, 진척률, "
            "마일스톤은 절대 생성하지 마세요. 입력에 존재하는 requirement_id와 artifact_type만 "
            "사용하세요. 요구사항 하나는 분석·설계·구현·테스트 등 여러 TASK에 연결할 수 있고, "
            "공통 작업 하나에 여러 요구사항을 연결할 수도 있습니다. 모든 요구사항은 최소 하나의 "
            "TASK에 연결하세요. 산출물은 실제로 작성하거나 갱신하는 TASK에 연결하세요. "
            "작업명, 설명과 완료 조건은 간결한 한국어로 작성하고 중복 작업은 합치세요. "
            "phase_name은 입력 methodology의 문자열과 정확히 같게 유지하세요."
        )
