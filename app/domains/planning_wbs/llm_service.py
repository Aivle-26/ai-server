from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from app.domains.planning_documents.schemas import ArtifactType


load_dotenv()

WBS_LLM_TIMEOUT_SECONDS = 300
WBSRequiredSkill = Literal[
    "DOCUMENT_ANALYSIS",
    "REQUIREMENTS_ANALYSIS",
    "ARCHITECTURE_DESIGN",
    "BACKEND_DEVELOPMENT",
    "FRONTEND_DEVELOPMENT",
    "MOBILE_DEVELOPMENT",
    "DATA_ENGINEERING",
    "SECURITY",
    "DATABASE",
    "ACCESSIBILITY",
    "TESTING",
    "DEVOPS",
]


class GeneratedWBSTask(BaseModel):
    name: str
    description: str
    mapped_requirement_ids: list[int] = Field(default_factory=list)
    related_artifact_types: list[ArtifactType] = Field(default_factory=list)
    completion_criteria: list[str] = Field(min_length=1, max_length=20)
    required_skills: list[WBSRequiredSkill] = Field(min_length=1, max_length=12)


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
        client = OpenAI(
            api_key=api_key,
            timeout=WBS_LLM_TIMEOUT_SECONDS,
            max_retries=1,
        )
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
            "각 말단 TASK는 담당자 한 명이 독립적으로 수행하고 완료할 수 있는 범위로 만드세요. "
            "서로 다른 전문 역할의 독립적인 구현 산출물이 한 작업에 포함되면 하나의 TASK에 "
            "여러 실행 역할을 넣지 말고, 상위 WORK_PACKAGE 아래 역할별 TASK로 분리하세요. 특히 "
            "BACKEND_DEVELOPMENT와 FRONTEND_DEVELOPMENT, BACKEND_DEVELOPMENT와 MOBILE_DEVELOPMENT, "
            "DATA_ENGINEERING과 FRONTEND_DEVELOPMENT처럼 담당자, 산출물, 완료 조건을 독립적으로 "
            "판단할 수 있는 역할은 분리하세요. 반면 보조 역량이 함께 필요한 단일 산출물은 불필요하게 "
            "분리하지 마세요. BACKEND_DEVELOPMENT와 SECURITY, DATA_ENGINEERING과 DATABASE, "
            "FRONTEND_DEVELOPMENT와 ACCESSIBILITY는 하나의 담당자가 수행하는 보조 역량일 수 있으므로 "
            "실제 산출물과 완료 조건이 분리될 때만 나누세요. 각 TASK의 required_skills에는 대표 실행 "
            "역할을 우선 하나만 지정하고, "
            "DOCUMENT_ANALYSIS, REQUIREMENTS_ANALYSIS, ARCHITECTURE_DESIGN, BACKEND_DEVELOPMENT, "
            "FRONTEND_DEVELOPMENT, MOBILE_DEVELOPMENT, DATA_ENGINEERING, SECURITY, DATABASE, "
            "ACCESSIBILITY, TESTING, DEVOPS 중에서만 선택하세요. 분리된 TASK에는 관련된 원래 "
            "requirement_id를 모두 보존하세요. "
            "phase_name은 입력 methodology의 문자열과 정확히 같게 유지하세요."
        )
