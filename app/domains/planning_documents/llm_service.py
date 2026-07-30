from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from time import perf_counter
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field

from .schemas import RequiredArtifact, RequirementCategory
from .settings import PlanningAnalysisSettings


load_dotenv()
logger = logging.getLogger("uvicorn.error")


class ExtractedProjectInfo(BaseModel):
    project_name: str | None = None
    project_goal: str | None = None
    client_organization: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    key_features: list[str] = Field(default_factory=list)
    required_artifacts: list[RequiredArtifact] = Field(default_factory=list)
    acceptance_conditions: list[str] = Field(default_factory=list)
    budget_contract_conditions: list[str] = Field(default_factory=list)
    security_privacy_conditions: list[str] = Field(default_factory=list)


class ExtractedRequirement(BaseModel):
    function_name: str
    requirement_text: str
    category: RequirementCategory = "UNSPECIFIED"
    priority: Literal["HIGH", "MEDIUM", "LOW", "UNSPECIFIED"] = "UNSPECIFIED"
    acceptance_criteria: str | None = None
    due_date: date | None = None
    deliverable_name: str | None = None
    security_condition: str | None = None
    source_document: str
    source_excerpt: str | None = None


class DocumentChunkExtraction(BaseModel):
    project_info: ExtractedProjectInfo
    requirements: list[ExtractedRequirement] = Field(default_factory=list, max_length=200)


@dataclass(frozen=True)
class PlanningLLMExtractionOutcome:
    text_partials: list[dict[str, Any]]
    vision_partials: list[dict[str, Any]]
    status: str
    call_count: int
    timed_out: bool
    fallback_used: bool

    @property
    def partials(self) -> list[dict[str, Any]]:
        return [*self.text_partials, *self.vision_partials]


class PlanningLLMExtractionService:
    def extract(
        self,
        chunks: list[dict[str, Any]],
        vision_documents: list[Any],
        fallback_extractions: list[dict[str, Any]],
        request_id: str = "untracked",
        settings: PlanningAnalysisSettings | None = None,
        deadline_monotonic: float | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        resolved_settings = settings or PlanningAnalysisSettings.from_env()
        resolved_deadline = (
            deadline_monotonic
            if deadline_monotonic is not None
            else (
                perf_counter()
                + resolved_settings.planning_analysis_timeout_seconds
            )
        )
        outcome = self.extract_with_metrics(
            chunks=chunks,
            vision_documents=vision_documents,
            fallback_extractions=fallback_extractions,
            request_id=request_id,
            settings=resolved_settings,
            deadline_monotonic=resolved_deadline,
        )
        return outcome.partials, outcome.status

    def extract_with_metrics(
        self,
        *,
        chunks: list[dict[str, Any]],
        vision_documents: list[Any],
        fallback_extractions: list[dict[str, Any]],
        request_id: str,
        settings: PlanningAnalysisSettings,
        deadline_monotonic: float,
    ) -> PlanningLLMExtractionOutcome:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if not api_key:
            self._audit(
                "fallback_used",
                request_id=request_id,
                model=model,
                reason="missing_api_key",
            )
            return PlanningLLMExtractionOutcome(
                text_partials=fallback_extractions,
                vision_partials=[],
                status="SKIPPED_NO_API_KEY",
                call_count=0,
                timed_out=False,
                fallback_used=True,
            )

        text_results: list[dict[str, Any]] = []
        vision_results: list[dict[str, Any]] = []
        used_fallback = False
        timed_out = False
        call_index = 0

        chunk_fallback_pairs = list(zip(
            chunks,
            fallback_extractions,
            strict=True,
        ))
        for index, (chunk, fallback) in enumerate(chunk_fallback_pairs):
            try:
                provider_timeout = self._remaining_provider_timeout(
                    deadline_monotonic
                )
                llm = ChatOpenAI(
                    model=model,
                    temperature=0,
                    api_key=api_key,
                    timeout=provider_timeout,
                    max_retries=(
                        settings.planning_analysis_retry_count
                    ),
                ).with_structured_output(DocumentChunkExtraction)
            except Exception as exc:
                self._audit(
                    "provider_call_failed",
                    request_id=request_id,
                    model=model,
                    call_index=0,
                    exception_type=type(exc).__name__,
                    phase="client_initialization",
                )
                self._audit(
                    "fallback_used",
                    request_id=request_id,
                    model=model,
                    reason=(
                        "analysis_timeout"
                        if self._is_timeout_error(exc)
                        else "client_initialization_failed"
                    ),
                )
                text_results.append(fallback)
                used_fallback = True
                if self._is_timeout_error(exc):
                    text_results.extend(
                        pair[1]
                        for pair in chunk_fallback_pairs[index + 1:]
                    )
                    timed_out = True
                    break
                continue

            call_index += 1
            started_at = perf_counter()
            self._audit(
                "provider_call_started",
                request_id=request_id,
                model=model,
                call_index=call_index,
            )
            try:
                result = llm.invoke([
                    SystemMessage(content=self._instructions()),
                    HumanMessage(
                        content=json.dumps(chunk, ensure_ascii=False)
                    ),
                ])
                self._audit(
                    "provider_call_succeeded",
                    request_id=request_id,
                    model=model,
                    call_index=call_index,
                    latency_ms=self._elapsed_ms(started_at),
                )
                text_results.append(self._normalize_result(
                    result.model_dump(mode="json"),
                    source_document=chunk["source_document"],
                    source_text=chunk["text"],
                ))
            except Exception as exc:
                self._audit(
                    "provider_call_failed",
                    request_id=request_id,
                    model=model,
                    call_index=call_index,
                    latency_ms=self._elapsed_ms(started_at),
                    exception_type=type(exc).__name__,
                )
                self._audit(
                    "fallback_used",
                    request_id=request_id,
                    model=model,
                    call_index=call_index,
                    reason=(
                        "analysis_timeout"
                        if self._is_timeout_error(exc)
                        else "provider_call_failed"
                    ),
                )
                text_results.append(fallback)
                used_fallback = True
                if self._is_timeout_error(exc):
                    text_results.extend(
                        pair[1]
                        for pair in chunk_fallback_pairs[index + 1:]
                    )
                    timed_out = True
                    break

        if not timed_out:
            for document in vision_documents:
                try:
                    provider_timeout = self._remaining_provider_timeout(
                        deadline_monotonic
                    )
                    client = OpenAI(
                        api_key=api_key,
                        timeout=provider_timeout,
                        max_retries=(
                            settings.planning_analysis_retry_count
                        ),
                    )
                except Exception as exc:
                    self._audit(
                        "provider_call_failed",
                        request_id=request_id,
                        model=model,
                        call_index=0,
                        exception_type=type(exc).__name__,
                        phase="client_initialization",
                    )
                    self._audit(
                        "fallback_used",
                        request_id=request_id,
                        model=model,
                        reason=(
                            "analysis_timeout"
                            if self._is_timeout_error(exc)
                            else "client_initialization_failed"
                        ),
                    )
                    used_fallback = True
                    if self._is_timeout_error(exc):
                        timed_out = True
                        break
                    continue

                call_index += 1
                started_at = perf_counter()
                self._audit(
                    "provider_call_started",
                    request_id=request_id,
                    model=model,
                    call_index=call_index,
                )
                try:
                    vision_results.append(
                        self._extract_pdf_with_vision(client, document)
                    )
                    self._audit(
                        "provider_call_succeeded",
                        request_id=request_id,
                        model=model,
                        call_index=call_index,
                        latency_ms=self._elapsed_ms(started_at),
                    )
                except Exception as exc:
                    self._audit(
                        "provider_call_failed",
                        request_id=request_id,
                        model=model,
                        call_index=call_index,
                        latency_ms=self._elapsed_ms(started_at),
                        exception_type=type(exc).__name__,
                    )
                    self._audit(
                        "fallback_used",
                        request_id=request_id,
                        model=model,
                        call_index=call_index,
                        reason=(
                            "analysis_timeout"
                            if self._is_timeout_error(exc)
                            else "provider_call_failed"
                        ),
                    )
                    used_fallback = True
                    if self._is_timeout_error(exc):
                        timed_out = True
                        break

        return PlanningLLMExtractionOutcome(
            text_partials=text_results,
            vision_partials=vision_results,
            status="FALLBACK" if used_fallback else "SUCCEEDED",
            call_count=call_index,
            timed_out=timed_out,
            fallback_used=used_fallback,
        )

    def _remaining_provider_timeout(
        self,
        deadline_monotonic: float,
    ) -> float:
        completion_reserve_seconds = 0.25
        remaining = (
            deadline_monotonic
            - perf_counter()
            - completion_reserve_seconds
        )
        if remaining <= 0:
            raise TimeoutError("planning analysis deadline reached")
        return remaining

    def _is_timeout_error(self, exception: Exception) -> bool:
        current: BaseException | None = exception
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            if (
                isinstance(current, TimeoutError)
                or "timeout" in type(current).__name__.casefold()
            ):
                return True
            current = current.__cause__ or current.__context__
        return False

    def _elapsed_ms(self, started_at: float) -> int:
        return round((perf_counter() - started_at) * 1000)

    def _audit(
        self,
        event: str,
        *,
        request_id: str,
        model: str,
        call_index: int | None = None,
        latency_ms: int | None = None,
        reason: str | None = None,
        exception_type: str | None = None,
        phase: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": event,
            "request_id": request_id,
            "model": model,
        }
        optional_fields = {
            "call_index": call_index,
            "latency_ms": latency_ms,
            "reason": reason,
            "exception_type": exception_type,
            "phase": phase,
        }
        payload.update({
            key: value
            for key, value in optional_fields.items()
            if value is not None
        })
        logger.info(
            "provider_audit %s",
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )

    def _extract_pdf_with_vision(self, client: OpenAI, document: Any) -> dict[str, Any]:
        encoded_pdf = base64.b64encode(document.content).decode("ascii")
        detail = os.getenv("OPENAI_PDF_DETAIL", "auto").lower()
        if detail not in {"auto", "low", "high"}:
            detail = "auto"

        response = client.responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            instructions=self._instructions(),
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": document.file_name,
                        "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                        "detail": detail,
                    },
                    {
                        "type": "input_text",
                        "text": (
                            f"이 PDF 문서({document.file_name}) 전체에서 프로젝트 기본정보와 "
                            "검수 가능한 요구사항 후보를 추출하세요."
                        ),
                    },
                ],
            }],
            text_format=DocumentChunkExtraction,
            store=False,
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI가 구조화된 PDF 분석 결과를 반환하지 않았습니다.")
        return self._normalize_result(
            response.output_parsed.model_dump(mode="json"),
            source_document=document.file_name,
            source_text=None,
        )

    def _normalize_result(
        self,
        extracted: dict[str, Any],
        source_document: str,
        source_text: str | None,
    ) -> dict[str, Any]:
        for requirement in extracted["requirements"]:
            requirement["source_document"] = source_document
            excerpt = requirement.get("source_excerpt")
            if source_text is not None and excerpt and excerpt not in source_text:
                requirement["source_excerpt"] = None
        return extracted

    def _instructions(self) -> str:
        return (
            "당신은 IT 프로젝트 기획 문서 분석가입니다. 제공된 원문에 명시된 사실만 추출하세요. "
            "추론하거나 없는 날짜·조건을 만들지 마세요. 요구사항은 독립적으로 검수 가능한 단위로 "
            "나누고, source_document는 입력 파일명과 정확히 같게 유지하세요. 우선순위가 명시되지 "
            "않으면 UNSPECIFIED를 사용하세요. 각 요구사항의 category는 다음 기준으로 하나만 선택하세요: "
            "FUNCTIONAL은 시스템 기능, NON_FUNCTIONAL은 성능·품질·가용성 같은 비기능, "
            "SECURITY는 보안·개인정보, DATA는 데이터 구조·저장·이관·품질, "
            "INTERFACE는 외부 시스템·API 연계, OPERATION은 운영·배포·모니터링·유지보수, "
            "PROJECT_MANAGEMENT는 일정·산출물·교육·보고·검수·사업관리, "
            "어느 분류에도 명확히 해당하지 않으면 UNSPECIFIED입니다. "
            "프로젝트 산출물은 project_info.required_artifacts에 넣으세요. artifact_type은 "
            "RFP, PROPOSAL, REQUIREMENTS_DEFINITION, FUNCTION_SPECIFICATION, WBS, ERD, "
            "MEETING_MINUTES, TEST_RESULTS, WEEKLY_REPORT, FINAL_REPORT, UI_DESIGN 중 하나만 "
            "사용하세요. 각각 RFP, 제안서, 요구사항 정의서, 기능 명세서, WBS, ERD, 회의록, "
            "테스트 결과서, 주간 보고서, 최종 보고서, UI 설계서를 뜻합니다. 문서에 산출물로 "
            "명시된 항목만 추출하고, 버전이 없으면 required_version은 1.0으로 작성하세요. "
            "acceptance_conditions, budget_contract_conditions, security_privacy_conditions의 "
            "각 항목은 원문의 의미를 유지하면서 짧은 명사형으로 정리하세요. 한 항목에는 하나의 "
            "조건만 넣고, 문장 끝의 '해야 한다', '하여야 한다', '한다'는 제거하세요. 예를 들어 "
            "'기능 테스트를 통과해야 한다'는 '기능 테스트 통과', '개인정보를 암호화해야 한다'는 "
            "'개인정보 암호화'로 작성하세요. "
            "source_excerpt에는 판단 근거가 되는 짧은 원문을 넣으세요."
        )
