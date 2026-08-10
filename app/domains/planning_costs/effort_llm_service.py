"""WBS별 KOSA 직무와 예상 인일을 추정하는 LLM 서비스."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator

from .effort_schemas import KosaDetailedJob


load_dotenv()


class GeneratedWBSEffort(BaseModel):
    wbs_id: int = Field(gt=0)
    detailed_job: KosaDetailedJob
    estimated_person_days: float = Field(ge=0.5, le=2_000)
    estimation_reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def normalize_effort(self) -> "GeneratedWBSEffort":
        self.estimation_reason = self.estimation_reason.strip()
        if not self.estimation_reason:
            raise ValueError("공수 산정 근거는 비어 있을 수 없습니다.")
        return self


class GeneratedOverlapCandidate(BaseModel):
    wbs_ids: list[int] = Field(min_length=2, max_length=10)
    reason: str = Field(min_length=1, max_length=500)
    recommendation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def normalize_candidate(self) -> "GeneratedOverlapCandidate":
        self.wbs_ids = list(dict.fromkeys(self.wbs_ids))
        self.reason = self.reason.strip()
        self.recommendation = self.recommendation.strip()
        if len(self.wbs_ids) < 2:
            raise ValueError("중복 후보에는 서로 다른 WBS가 두 개 이상 필요합니다.")
        if not self.reason or not self.recommendation:
            raise ValueError("중복 사유와 권고사항은 비어 있을 수 없습니다.")
        return self


class GeneratedEffortPlan(BaseModel):
    wbs_efforts: list[GeneratedWBSEffort] = Field(min_length=1, max_length=200)
    overlap_candidates: list[GeneratedOverlapCandidate] = Field(
        default_factory=list,
        max_length=100,
    )


class EffortLLMConfigurationError(RuntimeError):
    pass


class EffortLLMGenerationError(RuntimeError):
    pass


class PlanningEffortLLMService:
    MAX_TASKS_PER_BATCH = 30
    MAX_CONCURRENT_BATCHES = 3

    def generate(self, context: dict) -> GeneratedEffortPlan:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EffortLLMConfigurationError(
                "OPENAI_API_KEY가 설정되지 않았습니다."
            )

        try:
            batches = self._split_context(context)
            if len(batches) == 1:
                client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
                return self._request(client, batches[0])

            plans: list[GeneratedEffortPlan | None] = [None] * len(batches)
            with ThreadPoolExecutor(
                max_workers=min(self.MAX_CONCURRENT_BATCHES, len(batches))
            ) as executor:
                futures = {
                    executor.submit(self._generate_batch, api_key, batch): index
                    for index, batch in enumerate(batches)
                }
                for future in as_completed(futures):
                    plans[futures[future]] = future.result()
            return self._merge_plans([plan for plan in plans if plan is not None])
        except EffortLLMGenerationError:
            raise
        except Exception as exc:
            raise EffortLLMGenerationError(
                "OpenAI KOSA 직무·공수 산정 요청에 실패했습니다."
            ) from exc

    def _generate_batch(self, api_key: str, context: dict) -> GeneratedEffortPlan:
        client = OpenAI(api_key=api_key, timeout=60, max_retries=1)
        return self._request(client, context)

    def _split_context(self, context: dict) -> list[dict]:
        tasks = context.get("wbs_tasks", [])
        if len(tasks) <= self.MAX_TASKS_PER_BATCH:
            return [context]

        groups: dict[tuple, list[dict]] = {}
        for task in tasks:
            package_key = (
                "package",
                task["work_package_id"],
            ) if task.get("work_package_id") is not None else (
                "ungrouped",
                task["wbs_id"],
            )
            groups.setdefault(package_key, []).append(task)

        task_batches: list[list[dict]] = []
        current: list[dict] = []
        for group in groups.values():
            if len(group) <= self.MAX_TASKS_PER_BATCH:
                if current and len(current) + len(group) > self.MAX_TASKS_PER_BATCH:
                    task_batches.append(current)
                    current = []
                current.extend(group)
                continue

            if current:
                task_batches.append(current)
                current = []
            for offset in range(0, len(group), self.MAX_TASKS_PER_BATCH):
                chunk = group[offset:offset + self.MAX_TASKS_PER_BATCH]
                if len(chunk) == self.MAX_TASKS_PER_BATCH:
                    task_batches.append(chunk)
                else:
                    current = chunk
        if current:
            task_batches.append(current)

        return [
            {
                **context,
                "wbs_tasks": batch,
                "batch_index": index,
                "batch_count": len(task_batches),
            }
            for index, batch in enumerate(task_batches, start=1)
        ]

    def _merge_plans(
        self,
        plans: list[GeneratedEffortPlan],
    ) -> GeneratedEffortPlan:
        efforts = []
        candidates = []
        seen_candidates: set[tuple[int, ...]] = set()
        for plan in plans:
            efforts.extend(plan.wbs_efforts)
            for candidate in plan.overlap_candidates:
                key = tuple(sorted(candidate.wbs_ids))
                if key not in seen_candidates:
                    seen_candidates.add(key)
                    candidates.append(candidate)
        return GeneratedEffortPlan(
            wbs_efforts=efforts,
            overlap_candidates=candidates,
        )

    def _request(self, client: OpenAI, context: dict) -> GeneratedEffortPlan:
        try:
            response = client.responses.parse(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                instructions=self._instructions(),
                input=json.dumps(context, ensure_ascii=False),
                text_format=GeneratedEffortPlan,
                store=False,
            )
        except Exception as exc:
            raise EffortLLMGenerationError(
                "OpenAI가 WBS의 KOSA 직무와 공수를 산정하지 못했습니다."
            ) from exc

        if response.output_parsed is None:
            raise EffortLLMGenerationError(
                "OpenAI가 구조화된 KOSA 직무·공수 결과를 반환하지 않았습니다."
            )
        return response.output_parsed

    def _instructions(self) -> str:
        allowed_jobs = ", ".join(job.value for job in KosaDetailedJob)
        return (
            "당신은 IT 개발 프로젝트의 투입공수 산정 전문가입니다. 입력된 모든 WBS를 "
            "정확히 한 번씩 반환하세요. 각 WBS에 가장 적합한 KOSA 세부직무 한 개와 한 "
            "사람이 해당 작업을 완료하는 데 필요한 예상 인일을 산정하세요. 달력상 작업 "
            "기간을 그대로 공수로 사용하지 말고 작업 범위와 난이도를 기준으로 판단하세요. "
            "detailed_job은 다음 허용된 한글 값만 사용하세요: "
            f"{allowed_jobs}. 세부직무는 WBS의 실제 수행 내용으로 판단하고 기술 키워드 "
            "하나만으로 결정하지 마세요. 세부직무를 확정할 근거가 부족하면 해당 상위직무의 "
            "일반 직무를 사용하세요. 외부 AI API를 단순 호출하는 작업은 인공지능 SW "
            "개발자로 분류하지 말고, 모델·RAG·추천·추론 로직을 직접 구현하는 경우에만 "
            "인공지능 SW 개발자를 선택하세요. MM, 담당자, 단가, 인건비와 최종 견적 금액은 "
            "생성하지 마세요. estimation_reason은 세부직무 선택과 공수 판단 근거가 드러나는 "
            "간결한 한국어 한 문장으로 작성하고 confidence는 근거의 충분성에 따라 0부터 "
            "1 사이로 반환하세요."
            " 같은 결과 묶음 안에서 설명과 산출물이 실질적으로 같은 WBS가 있으면 "
            "overlap_candidates에 WBS ID, 중복 사유, 합치거나 범위를 분리하는 권고를 반환하세요. "
            "직무가 같다는 이유만으로 중복 처리하지 말고, 중복 후보를 임의로 삭제하거나 공수에서 빼지 마세요."
        )
