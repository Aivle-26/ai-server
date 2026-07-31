from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field

from .schemas import RequiredArtifact, RequirementCategory


load_dotenv()

logger = logging.getLogger(__name__)
MAX_EXTRACTION_WORKERS = 2
REPAIR_BATCH_SIZE = 10
SOURCE_CONTEXT_SIZE = 2_000


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


class RepairedRequirement(ExtractedRequirement):
    original_requirement_id: int = Field(gt=0)


class RequirementRepairResult(BaseModel):
    requirements: list[RepairedRequirement] = Field(default_factory=list, max_length=100)


class PlanningLLMExtractionService:
    def extract(
        self,
        chunks: list[dict[str, Any]],
        vision_documents: list[Any],
        fallback_extractions: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return fallback_extractions, "SKIPPED_NO_API_KEY"

        results: list[dict[str, Any]] = []
        used_fallback = False

        if chunks:
            try:
                llm = ChatOpenAI(
                    model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                    temperature=0,
                    api_key=api_key,
                    timeout=60,
                    max_retries=2,
                ).with_structured_output(DocumentChunkExtraction)
                chunk_results: list[dict[str, Any] | None] = [None] * len(chunks)
                workers = min(MAX_EXTRACTION_WORKERS, len(chunks))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {
                        executor.submit(self._extract_chunk, llm, chunk): (
                            index,
                            chunk,
                            fallback,
                        )
                        for index, (chunk, fallback) in enumerate(
                            zip(chunks, fallback_extractions, strict=True)
                        )
                    }
                    for future in as_completed(futures):
                        index, chunk, fallback = futures[future]
                        try:
                            chunk_results[index] = future.result()
                        except Exception as exc:
                            logger.warning(
                                "문서 청크 LLM 추출 실패: document=%s, chunk=%s, error=%s",
                                chunk["source_document"],
                                chunk["chunk_index"],
                                type(exc).__name__,
                            )
                            chunk_results[index] = fallback
                            used_fallback = True
                results.extend(
                    result for result in chunk_results
                    if result is not None
                )
            except Exception as exc:
                logger.warning("문서 LLM 초기화 실패: error=%s", type(exc).__name__)
                results.extend(fallback_extractions)
                used_fallback = True

        if vision_documents:
            try:
                client = OpenAI(api_key=api_key, timeout=120, max_retries=2)
                for document in vision_documents:
                    started_at = time.perf_counter()
                    try:
                        results.append(self._extract_pdf_with_vision(client, document))
                        logger.info(
                            "PDF 비전 추출 완료: document=%s, elapsed_seconds=%.3f",
                            document.file_name,
                            time.perf_counter() - started_at,
                        )
                    except Exception as exc:
                        logger.warning(
                            "PDF 비전 추출 실패: document=%s, error=%s",
                            document.file_name,
                            type(exc).__name__,
                        )
                        used_fallback = True
            except Exception as exc:
                logger.warning("PDF 비전 클라이언트 초기화 실패: error=%s", type(exc).__name__)
                used_fallback = True

        return results, "FALLBACK" if used_fallback else "SUCCEEDED"

    def _extract_chunk(
        self,
        llm: Any,
        chunk: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        result = llm.invoke([
            SystemMessage(content=self._instructions()),
            HumanMessage(content=json.dumps(chunk, ensure_ascii=False)),
        ])
        normalized = self._normalize_result(
            result.model_dump(mode="json"),
            source_document=chunk["source_document"],
            source_text=chunk["text"],
        )
        logger.info(
            "문서 청크 LLM 추출 완료: document=%s, chunk=%s, blocks=%s, "
            "characters=%s, requirements=%s, elapsed_seconds=%.3f",
            chunk["source_document"],
            chunk["chunk_index"],
            len(chunk.get("blocks") or []),
            len(chunk["text"]),
            len(normalized["requirements"]),
            time.perf_counter() - started_at,
        )
        return normalized

    def repair_requirements(
        self,
        requirements: list[dict[str, Any]],
        validation_errors: dict[int, list[str]],
        source_texts: dict[str, str],
    ) -> tuple[list[dict[str, Any]], bool]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or not requirements:
            return [], False

        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                temperature=0,
                api_key=api_key,
                timeout=60,
                max_retries=2,
            ).with_structured_output(RequirementRepairResult)
        except Exception as exc:
            logger.warning("요구사항 재생성 LLM 초기화 실패: error=%s", type(exc).__name__)
            return [], False

        repaired: list[dict[str, Any]] = []
        originals = {
            int(requirement["requirement_id"]): requirement
            for requirement in requirements
        }
        for start in range(0, len(requirements), REPAIR_BATCH_SIZE):
            batch = requirements[start:start + REPAIR_BATCH_SIZE]
            payload = [
                {
                    "original_requirement_id": requirement["requirement_id"],
                    "validation_errors": validation_errors.get(
                        int(requirement["requirement_id"]),
                        [],
                    ),
                    "requirement": requirement,
                    "source_context": self._source_context(requirement, source_texts),
                }
                for requirement in batch
            ]
            started_at = time.perf_counter()
            try:
                result = llm.invoke([
                    SystemMessage(content=self._repair_instructions()),
                    HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
                ])
            except Exception as exc:
                logger.warning(
                    "요구사항 선택 재생성 실패: batch_start=%s, error=%s",
                    start,
                    type(exc).__name__,
                )
                return [], False
            logger.info(
                "요구사항 선택 재생성 완료: input=%s, output=%s, elapsed_seconds=%.3f",
                len(batch),
                len(result.requirements),
                time.perf_counter() - started_at,
            )

            for item in result.requirements:
                item_data = item.model_dump(mode="json")
                original_id = int(item_data.pop("original_requirement_id"))
                original = originals.get(original_id)
                if original is None:
                    continue
                item_data["source_document"] = original["source_document"]
                item_data["original_requirement_id"] = original_id
                repaired.append(item_data)
        return repaired, True

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
            if (
                source_text is not None
                and excerpt
                and self._comparison_text(excerpt)
                not in self._comparison_text(source_text)
            ):
                requirement["source_excerpt"] = None
        return extracted

    def _comparison_text(self, value: Any) -> str:
        return "".join(str(value or "").split())

    def _instructions(self) -> str:
        return (
            "당신은 IT 프로젝트 기획 문서 분석가입니다. 제공된 원문에 명시된 사실만 추출하세요. "
            "추론하거나 없는 날짜·조건을 만들지 마세요. 요구사항은 독립적으로 검수 가능한 단위로 "
            "나누고, source_document는 입력 파일명과 정확히 같게 유지하세요. 입력의 blocks는 "
            "요구사항 코드, 글머리표, 표 행, 번호 목록, 일반 문단의 경계를 표시합니다. 서로 다른 "
            "block_id의 내용을 하나로 합치지 마세요. 한 블록 안에서도 조회, 등록, 수정, 삭제, "
            "시각화처럼 각각 독립적으로 검수할 수 있는 동작은 별도 요구사항으로 나누세요. 원문에 "
            "문법 오류가 있으면 의미와 조건을 바꾸지 않는 범위에서 완결된 요구사항 문장으로 "
            "교정하세요. 표 머리글, 페이지 번호, 입찰 참가 자격, 실적 증빙서류, 평가 서식 작성 "
            "방법은 requirement 후보로 추출하지 마세요. 계약 이행 이후 적용되는 산출물, 검수, "
            "보안, 운영 조건은 요구사항으로 유지하세요. source_excerpt에는 해당 block.text에 "
            "실제로 존재하는 짧은 원문을 그대로 넣으세요. 우선순위가 명시되지 않으면 "
            "UNSPECIFIED를 사용하세요. 각 요구사항의 category는 다음 기준으로 하나만 선택하세요: "
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
            "'개인정보 암호화'로 작성하세요."
        )

    def _repair_instructions(self) -> str:
        return (
            "당신은 IT 프로젝트 요구사항 품질 교정 담당자입니다. 입력에는 품질 검증에 실패한 "
            "요구사항만 있습니다. validation_errors와 source_context를 근거로 해당 항목만 다시 "
            "작성하세요. 입력에 없는 사실은 만들지 마세요. 표 머리글이나 요구사항 번호를 기능명으로 "
            "사용하지 말고, 여러 요구사항이 합쳐졌다면 독립적으로 검수 가능한 항목으로 분리하세요. "
            "분리한 결과에는 같은 original_requirement_id를 사용하세요. source_excerpt는 "
            "source_context에 실제 존재하는 짧은 원문을 그대로 사용하세요. 근거가 없는 항목은 "
            "결과에서 제외하세요. category와 priority는 허용된 enum만 사용하고, 우선순위가 "
            "명시되지 않았으면 UNSPECIFIED를 사용하세요."
        )

    def _source_context(
        self,
        requirement: dict[str, Any],
        source_texts: dict[str, str],
    ) -> str:
        source_document = str(requirement.get("source_document") or "")
        source_text = source_texts.get(source_document, "")
        if not source_text:
            return ""

        candidates = [
            str(requirement.get("source_excerpt") or "").strip(),
            *re.findall(
                r"\b(?:REQ|[A-Z]{2,5})[-_ ]\d{2,4}\b",
                str(requirement.get("requirement_text") or ""),
                re.I,
            ),
            str(requirement.get("function_name") or "").strip(),
        ]
        position = next(
            (
                source_text.find(candidate)
                for candidate in candidates
                if candidate and source_text.find(candidate) >= 0
            ),
            0,
        )
        half = SOURCE_CONTEXT_SIZE // 2
        start = max(0, position - half)
        end = min(len(source_text), start + SOURCE_CONTEXT_SIZE)
        return source_text[start:end]
