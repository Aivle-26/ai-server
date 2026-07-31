from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


REQUIREMENT_CODE_PATTERN = re.compile(r"\b(?:REQ|[A-Z]{2,5})[-_ ]\d{2,4}\b", re.I)
TABLE_HEADER_MARKERS = (
    "요구사항 고유번호",
    "요구사항고유번호",
    "요구사항 명칭",
    "요구사항명칭",
    "요구사항 분류",
    "요구사항분류",
    "요구사항 상세설명",
    "요구사항상세설명",
)
PLACEHOLDER_FUNCTION_NAMES = {
    "",
    "공통",
    "기타",
    "미정",
    "요구사항",
    "요구사항명칭",
    "요구사항분류",
    "요구사항상세설명",
    "번호",
}


@dataclass(frozen=True)
class RequirementValidationIssue:
    requirement_id: int
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class RequirementQualityValidator:
    def validate(
        self,
        requirements: list[dict[str, Any]],
        source_texts: dict[str, str],
    ) -> list[RequirementValidationIssue]:
        issues: list[RequirementValidationIssue] = []
        for requirement in requirements:
            errors, warnings = self._validate_requirement(requirement, source_texts)
            if errors or warnings:
                issues.append(RequirementValidationIssue(
                    requirement_id=int(requirement["requirement_id"]),
                    errors=tuple(errors),
                    warnings=tuple(warnings),
                ))
        return issues

    def _validate_requirement(
        self,
        requirement: dict[str, Any],
        source_texts: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        function_name = self._clean(requirement.get("function_name"))
        requirement_text = self._clean(requirement.get("requirement_text"))
        source_document = self._clean(requirement.get("source_document"))
        source_excerpt = self._clean(requirement.get("source_excerpt"))

        if (
            function_name in PLACEHOLDER_FUNCTION_NAMES
            or re.fullmatch(r"번호\s*[A-Z]{2,5}", function_name, re.I)
        ):
            errors.append("기능명이 표 머리글 또는 임시값입니다.")
        elif len(function_name) > 100:
            errors.append("기능명이 지나치게 깁니다.")

        if len(requirement_text) < 10:
            errors.append("요구사항 본문이 지나치게 짧습니다.")
        elif len(requirement_text) > 1_500:
            errors.append("요구사항 본문이 지나치게 깁니다.")

        header_count = sum(
            marker in requirement_text or marker in function_name
            for marker in TABLE_HEADER_MARKERS
        )
        if header_count >= 2:
            errors.append("요구사항에 표 머리글이 섞여 있습니다.")

        if len(set(REQUIREMENT_CODE_PATTERN.findall(requirement_text))) > 1:
            errors.append("여러 요구사항이 한 항목에 합쳐져 있습니다.")

        if not source_document:
            errors.append("원본 문서명이 없습니다.")
        if not source_excerpt:
            warnings.append("판단 근거 원문이 없습니다.")
        else:
            source_text = source_texts.get(source_document, "")
            if (
                source_text
                and self._comparison_text(source_excerpt)
                not in self._comparison_text(source_text)
            ):
                warnings.append("판단 근거가 원본 문서에서 정확히 확인되지 않습니다.")

        return errors, warnings

    def _clean(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _comparison_text(self, value: Any) -> str:
        return re.sub(r"[\s\u00a0]+", "", str(value or "")).strip()


class RequirementSentenceNormalizer:
    def normalize(
        self,
        requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for requirement in requirements:
            item = dict(requirement)
            item["function_name"] = self._normalize_function_name(item.get("function_name"))
            item["requirement_text"] = self._normalize_sentence(item.get("requirement_text"))
            for field in (
                "acceptance_criteria",
                "deliverable_name",
                "security_condition",
            ):
                if item.get(field) is not None:
                    item[field] = self._normalize_optional_text(item[field])
            if item.get("source_excerpt") is not None:
                item["source_excerpt"] = str(item["source_excerpt"]).strip()

            key = re.sub(r"[\W_]+", "", item["requirement_text"]).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            normalized.append(item)
        return normalized

    def _normalize_function_name(self, value: Any) -> str:
        text = self._collapse(value)
        text = re.sub(r"^[\-–—•·❍○●◦▪▫]+\s*", "", text)
        return text.strip(" \t:：;,.。")

    def _normalize_sentence(self, value: Any) -> str:
        text = self._collapse(value)
        text = re.sub(
            r"^(?:요구사항\s*)?(?:REQ|[A-Z]{2,5})[-_ ]\d{2,4}\s*[:：.\-–—]?\s*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(r"^[\-–—•·❍○●◦▪▫]+\s*", "", text)
        text = re.sub(r"([.!?。])\1+", r"\1", text).strip()
        text = re.sub(r"구현하다(?=[.!?。]?$)", "구현한다", text)
        if text and text[-1] not in ".!?。":
            text = f"{text}."
        return text

    def _normalize_optional_text(self, value: Any) -> str | None:
        text = self._collapse(value).strip(" \t-–—•·;,.。")
        return text or None

    def _collapse(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()
