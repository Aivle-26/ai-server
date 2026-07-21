from __future__ import annotations

import base64
import json
import os
from datetime import date
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv()


class ExtractedProjectInfo(BaseModel):
    project_name: str | None = None
    project_goal: str | None = None
    client_organization: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    key_features: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_conditions: list[str] = Field(default_factory=list)
    budget_contract_conditions: list[str] = Field(default_factory=list)
    security_privacy_conditions: list[str] = Field(default_factory=list)


class ExtractedRequirement(BaseModel):
    function_name: str
    requirement_text: str
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
                for chunk, fallback in zip(chunks, fallback_extractions, strict=True):
                    try:
                        result = llm.invoke([
                            SystemMessage(content=self._instructions()),
                            HumanMessage(content=json.dumps(chunk, ensure_ascii=False)),
                        ])
                        results.append(self._normalize_result(
                            result.model_dump(mode="json"),
                            source_document=chunk["source_document"],
                            source_text=chunk["text"],
                        ))
                    except Exception:
                        results.append(fallback)
                        used_fallback = True
            except Exception:
                results.extend(fallback_extractions)
                used_fallback = True

        if vision_documents:
            try:
                client = OpenAI(api_key=api_key, timeout=120, max_retries=2)
                for document in vision_documents:
                    try:
                        results.append(self._extract_pdf_with_vision(client, document))
                    except Exception:
                        used_fallback = True
            except Exception:
                used_fallback = True

        return results, "FALLBACK" if used_fallback else "SUCCEEDED"

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
            "않으면 UNSPECIFIED를 사용하세요. source_excerpt에는 판단 근거가 되는 짧은 원문을 넣으세요."
        )
