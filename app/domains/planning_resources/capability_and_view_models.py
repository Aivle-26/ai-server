from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from .schemas import MemberAllocation, MemberSkill, ProjectMemberCandidate


class AssessmentStatus(StrEnum):
    DECLARED = "DECLARED"
    INFERRED = "INFERRED"
    CONFIRMED = "CONFIRMED"


class Evidence(BaseModel):
    source_type: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    description: str = Field(min_length=1)
    observed_at: datetime | None = None

    @field_validator(
        "source_type",
        "source_reference",
        "description",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("evidence text fields must be strings")
        normalized = value.strip()
        if not normalized:
            raise ValueError("evidence text fields cannot be blank")
        return normalized


class SkillAssessment(BaseModel):
    skill_code: str
    proficiency_level: int = Field(ge=1, le=5)
    experience_months: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidences: list[Evidence] = Field(default_factory=list)
    status: AssessmentStatus

    @field_validator("skill_code", mode="before")
    @classmethod
    def normalize_skill_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("skill_code must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("skill_code cannot be empty or whitespace")
        return normalized

    @model_validator(mode="after")
    def validate_skill(self) -> SkillAssessment:
        if self.status == AssessmentStatus.INFERRED and not self.evidences:
            raise ValueError(
                f"INFERRED skill ({self.skill_code}) requires evidence"
            )
        return self


class RoleAssessment(BaseModel):
    role_code: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidences: list[Evidence] = Field(default_factory=list)
    status: AssessmentStatus

    @field_validator("role_code", mode="before")
    @classmethod
    def normalize_role_code(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("role_code must be a string")
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("role_code cannot be empty or whitespace")
        return normalized

    @model_validator(mode="after")
    def validate_role(self) -> RoleAssessment:
        if self.status == AssessmentStatus.INFERRED and not self.evidences:
            raise ValueError(
                f"INFERRED role ({self.role_code}) requires evidence"
            )
        return self


class MemberCapabilityProfile(BaseModel):
    project_member_id: int = Field(gt=0)
    primary_roles: list[RoleAssessment] = Field(default_factory=list)
    secondary_roles: list[RoleAssessment] = Field(default_factory=list)
    skills: list[SkillAssessment] = Field(default_factory=list)
    domain_experience: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    development_needs: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    profile_confidence: float = Field(ge=0.0, le=1.0)
    profile_version: int = Field(gt=0, default=1)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now().astimezone()
    )

    @model_validator(mode="after")
    def validate_profile(self) -> MemberCapabilityProfile:
        self._reject_duplicate_role_assessments(
            self.primary_roles,
            "primary_roles",
        )
        self._reject_duplicate_role_assessments(
            self.secondary_roles,
            "secondary_roles",
        )

        primary_codes = {role.role_code for role in self.primary_roles}
        secondary_codes = {role.role_code for role in self.secondary_roles}
        overlapping_codes = sorted(primary_codes & secondary_codes)
        if overlapping_codes:
            raise ValueError(
                "A role_code cannot be both primary and secondary: "
                + ", ".join(overlapping_codes)
            )

        skill_seen: set[tuple[str, AssessmentStatus]] = set()
        for skill in self.skills:
            key = (skill.skill_code, skill.status)
            if key in skill_seen:
                raise ValueError(
                    "Duplicate skill entry: "
                    f"({skill.skill_code}, {skill.status.value})"
                )
            skill_seen.add(key)
        return self

    @staticmethod
    def _reject_duplicate_role_assessments(
        roles: Sequence[RoleAssessment],
        area_name: str,
    ) -> None:
        seen: set[tuple[str, AssessmentStatus]] = set()
        for role in roles:
            key = (role.role_code, role.status)
            if key in seen:
                raise ValueError(
                    f"Duplicate role entry in {area_name}: "
                    f"({role.role_code}, {role.status.value})"
                )
            seen.add(key)


class AssessmentExclusion(BaseModel):
    code: str = Field(min_length=1)
    status: AssessmentStatus
    confidence: float = Field(ge=0.0, le=1.0)
    proficiency_level: int | None = Field(default=None, ge=1, le=5)
    reason: str = Field(min_length=1)


class AdapterResult(BaseModel):
    eligible: bool
    candidate: ProjectMemberCandidate | None = None
    selected_role_assessments: list[RoleAssessment] = Field(
        default_factory=list
    )
    selected_skill_assessments: list[SkillAssessment] = Field(
        default_factory=list
    )
    excluded_roles: list[AssessmentExclusion] = Field(default_factory=list)
    excluded_skills: list[AssessmentExclusion] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


AssessmentT = TypeVar("AssessmentT", RoleAssessment, SkillAssessment)


def _assessment_code(assessment: RoleAssessment | SkillAssessment) -> str:
    if isinstance(assessment, SkillAssessment):
        return assessment.skill_code
    return assessment.role_code


def _is_higher_priority(
    candidate: RoleAssessment | SkillAssessment,
    current: RoleAssessment | SkillAssessment,
) -> bool:
    candidate_confirmed = candidate.status == AssessmentStatus.CONFIRMED
    current_confirmed = current.status == AssessmentStatus.CONFIRMED
    if candidate_confirmed != current_confirmed:
        return candidate_confirmed
    return candidate.confidence > current.confidence


def _exclusion(
    assessment: RoleAssessment | SkillAssessment,
    reason: str,
) -> AssessmentExclusion:
    proficiency_level = (
        assessment.proficiency_level
        if isinstance(assessment, SkillAssessment)
        else None
    )
    return AssessmentExclusion(
        code=_assessment_code(assessment),
        status=assessment.status,
        confidence=assessment.confidence,
        proficiency_level=proficiency_level,
        reason=reason,
    )


def _resolve_best_assessments(
    assessments: Sequence[AssessmentT],
    confidence_threshold: float,
) -> tuple[list[AssessmentT], list[AssessmentExclusion]]:
    selected_by_code: dict[str, AssessmentT] = {}
    exclusions: list[AssessmentExclusion] = []

    for assessment in assessments:
        code = _assessment_code(assessment)
        if (
            assessment.status != AssessmentStatus.CONFIRMED
            and assessment.confidence < confidence_threshold
        ):
            exclusions.append(
                _exclusion(assessment, "Confidence below threshold")
            )
            continue

        current = selected_by_code.get(code)
        if current is None:
            selected_by_code[code] = assessment
            continue

        if _is_higher_priority(assessment, current):
            exclusions.append(
                _exclusion(
                    current,
                    "Superseded by a higher-priority assessment",
                )
            )
            selected_by_code[code] = assessment
        else:
            exclusions.append(
                _exclusion(
                    assessment,
                    "An equal- or higher-priority assessment was retained",
                )
            )

    return list(selected_by_code.values()), exclusions


def to_project_member_candidate(
    profile: MemberCapabilityProfile,
    allocations: list[MemberAllocation],
    confidence_threshold: float = 0.7,
) -> AdapterResult:
    selected_roles, excluded_roles = _resolve_best_assessments(
        [*profile.primary_roles, *profile.secondary_roles],
        confidence_threshold,
    )
    selected_skills, excluded_skills = _resolve_best_assessments(
        profile.skills,
        confidence_threshold,
    )

    candidate = None
    rejection_reasons: list[str] = []
    if not selected_roles:
        rejection_reasons.append("No eligible roles found.")
    else:
        candidate = ProjectMemberCandidate(
            project_member_id=profile.project_member_id,
            roles=[role.role_code for role in selected_roles],
            skills=[
                MemberSkill(
                    skill_code=skill.skill_code,
                    proficiency_level=skill.proficiency_level,
                    experience_months=skill.experience_months,
                )
                for skill in selected_skills
            ],
            allocations=allocations,
        )

    return AdapterResult(
        eligible=not rejection_reasons,
        candidate=candidate,
        selected_role_assessments=selected_roles,
        selected_skill_assessments=selected_skills,
        excluded_roles=excluded_roles,
        excluded_skills=excluded_skills,
        rejection_reasons=rejection_reasons,
    )
