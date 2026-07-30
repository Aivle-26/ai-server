from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .schemas import ExistingRequirement, RequirementCandidate


class RequirementReadjustmentService:
    _REMOVAL_TERMS = (
        "삭제",
        "제외",
        "취소",
        "폐기",
        "중단",
        "remove",
        "exclude",
        "cancel",
        "deprecate",
    )

    def build_changes(
        self,
        existing_requirements: list[ExistingRequirement],
        extracted_requirements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        proposed = [
            RequirementCandidate.model_validate(requirement)
            for requirement in extracted_requirements
        ]
        matched_proposed: set[int] = set()
        changes: list[dict[str, Any]] = []

        for existing in existing_requirements:
            exact_index = self._find_exact(existing, proposed, matched_proposed)
            if exact_index is not None:
                matched_proposed.add(exact_index)
                candidate = proposed[exact_index]
                changes.append(self._change(
                    existing=existing,
                    proposed=candidate,
                    change_type="UNCHANGED",
                    reason="추가 문서에서 동일한 요구사항이 확인되었습니다.",
                ))
                continue

            removal_index = self._find_explicit_removal(
                existing,
                proposed,
                matched_proposed,
            )
            if removal_index is not None:
                matched_proposed.add(removal_index)
                removal_evidence = proposed[removal_index]
                changes.append(self._change(
                    existing=existing,
                    proposed=None,
                    change_type="REMOVED",
                    reason="추가 문서에 기존 요구사항의 삭제 또는 제외가 명시되었습니다.",
                    evidences=removal_evidence.evidences,
                ))
                continue

            modified_index = self._find_similar(
                existing,
                proposed,
                matched_proposed,
            )
            if modified_index is not None:
                matched_proposed.add(modified_index)
                candidate = proposed[modified_index]
                changes.append(self._change(
                    existing=existing,
                    proposed=candidate,
                    change_type="MODIFIED",
                    reason="기존 요구사항과 유사하지만 내용이 달라 PM 검토가 필요합니다.",
                ))
                continue

            changes.append(self._change(
                existing=existing,
                proposed=None,
                change_type="UNCHANGED",
                reason=(
                    "추가 문서에 명시적인 변경 또는 삭제 근거가 없어 "
                    "기존 요구사항을 유지합니다."
                ),
            ))

        for index, candidate in enumerate(proposed):
            if index in matched_proposed:
                continue
            changes.append(self._change(
                existing=None,
                proposed=candidate,
                change_type="ADDED",
                reason="추가 문서에서 새 요구사항이 도출되었습니다.",
            ))

        for index, change in enumerate(changes, start=1):
            change["candidate_id"] = f"CHG-{index:03d}"
        return changes

    def _find_exact(
        self,
        existing: ExistingRequirement,
        proposed: list[RequirementCandidate],
        matched: set[int],
    ) -> int | None:
        normalized = self._normalize(existing.requirement_text)
        for index, candidate in enumerate(proposed):
            if (
                index not in matched
                and self._normalize(candidate.requirement_text) == normalized
                and self._metadata_is_compatible(existing, candidate)
            ):
                return index
        return None

    def _metadata_is_compatible(
        self,
        existing: ExistingRequirement,
        candidate: RequirementCandidate,
    ) -> bool:
        if (
            candidate.category != "UNSPECIFIED"
            and candidate.category != existing.category
        ):
            return False
        if (
            candidate.priority != "UNSPECIFIED"
            and candidate.priority != existing.priority
        ):
            return False
        optional_fields = (
            "acceptance_criteria",
            "due_date",
            "deliverable_name",
            "security_condition",
        )
        return all(
            getattr(candidate, field) is None
            or getattr(candidate, field) == getattr(existing, field)
            for field in optional_fields
        )

    def _find_similar(
        self,
        existing: ExistingRequirement,
        proposed: list[RequirementCandidate],
        matched: set[int],
    ) -> int | None:
        best_index = None
        best_score = 0.0
        existing_text = self._normalize(existing.requirement_text)
        existing_name = self._normalize(existing.function_name)
        for index, candidate in enumerate(proposed):
            if index in matched or self._contains_removal_term(
                candidate.requirement_text
            ):
                continue
            score = SequenceMatcher(
                None,
                existing_text,
                self._normalize(candidate.requirement_text),
            ).ratio()
            if (
                existing.category == candidate.category
                and existing.category != "UNSPECIFIED"
            ):
                score += 0.08
            if existing_name and existing_name == self._normalize(
                candidate.function_name
            ):
                score += 0.12
            if score > best_score:
                best_index = index
                best_score = score
        return best_index if best_score >= 0.62 else None

    def _find_explicit_removal(
        self,
        existing: ExistingRequirement,
        proposed: list[RequirementCandidate],
        matched: set[int],
    ) -> int | None:
        name = self._normalize(existing.function_name)
        text_tokens = {
            token
            for token in re.split(r"\W+", self._normalize(
                existing.requirement_text
            ))
            if len(token) >= 3
        }
        for index, candidate in enumerate(proposed):
            if index in matched:
                continue
            candidate_text = self._normalize(candidate.requirement_text)
            if not self._contains_removal_term(candidate_text):
                continue
            candidate_tokens = {
                token
                for token in re.split(r"\W+", candidate_text)
                if len(token) >= 3
            }
            matched_tokens = text_tokens & candidate_tokens
            identifies_requirement = (
                bool(len(name) >= 3 and name in candidate_text)
                or len(matched_tokens) >= 2
            )
            if identifies_requirement:
                return index
        return None

    def _change(
        self,
        *,
        existing: ExistingRequirement | None,
        proposed: RequirementCandidate | None,
        change_type: str,
        reason: str,
        evidences: list[Any] | None = None,
    ) -> dict[str, Any]:
        evidence_models = evidences
        if evidence_models is None:
            evidence_models = (
                proposed.evidences
                if proposed is not None
                else []
            )
        return {
            "candidate_id": "",
            "existing_requirement_id": (
                existing.requirement_id if existing is not None else None
            ),
            "change_type": change_type,
            "change_reason": reason,
            "existing_requirement": (
                existing.model_dump(mode="json")
                if existing is not None
                else None
            ),
            "proposed_requirement": (
                proposed.model_dump(mode="json")
                if proposed is not None
                else None
            ),
            "evidences": [
                evidence.model_dump(mode="json")
                if hasattr(evidence, "model_dump")
                else evidence
                for evidence in evidence_models
            ],
            "review_status": "PENDING_REVIEW",
        }

    def _contains_removal_term(self, value: str) -> bool:
        lowered = value.casefold()
        return any(term in lowered for term in self._REMOVAL_TERMS)

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()
