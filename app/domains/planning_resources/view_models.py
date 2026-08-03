"""Validated, JSON-serializable planning view models.

The models in this module intentionally contain no assignment or scheduling
logic.  They validate view data built from the production planning-resource
contracts and from explicitly supplied view metadata.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


PositiveId = Annotated[int, Field(gt=0)]


def _nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    return normalized


def _normalized_code(value: object, field_name: str) -> str:
    return _nonblank(value, field_name).upper()


def _normalize_text_list(values: list[object], field_name: str) -> list[str]:
    normalized = [_nonblank(value, field_name) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return normalized


def _ensure_unique(values: list[object], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} cannot contain duplicates")


class OrganizationTeamMetadata(BaseModel):
    """Optional, explicit organization facts that assignments do not contain.

    Relationships are keyed by real assignment role codes.  When this metadata
    is absent the builder leaves leaders and relationships empty instead of
    inferring an organization hierarchy.
    """

    model_config = ConfigDict(extra="forbid")

    role_code: str
    team_name: str | None = None
    leader_member_id: PositiveId | None = None
    reports_to_role_code: str | None = None
    collaborates_with_role_codes: list[str] = Field(default_factory=list)

    @field_validator("role_code", "reports_to_role_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: object) -> object:
        if value is None:
            return None
        return _normalized_code(value, "role_code")

    @field_validator("team_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if value is None:
            return None
        return _nonblank(value, "team_name")

    @field_validator("collaborates_with_role_codes", mode="before")
    @classmethod
    def normalize_collaborators(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized = [
            _normalized_code(item, "collaborates_with_role_codes")
            for item in value
        ]
        _ensure_unique(normalized, "collaborates_with_role_codes")
        return normalized

    @model_validator(mode="after")
    def reject_self_relationships(self) -> "OrganizationTeamMetadata":
        if self.reports_to_role_code == self.role_code:
            raise ValueError("a team cannot report to itself")
        if self.role_code in self.collaborates_with_role_codes:
            raise ValueError("a team cannot collaborate with itself")
        return self


class OrganizationMetadata(BaseModel):
    """Explicit organization facts not available in planning assignments."""

    model_config = ConfigDict(extra="forbid")

    project_manager_member_id: PositiveId | None = None
    teams: list[OrganizationTeamMetadata] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_roles(self) -> "OrganizationMetadata":
        roles = [team.role_code for team in self.teams]
        _ensure_unique(roles, "organization metadata role codes")
        return self


class OrganizationTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str
    team_name: str
    leader_member_id: PositiveId | None = None
    member_ids: list[PositiveId] = Field(default_factory=list)
    primary_roles: list[str] = Field(default_factory=list)
    secondary_roles: list[str] = Field(default_factory=list)
    assigned_wbs_ids: list[PositiveId] = Field(default_factory=list)
    reports_to: str | None = None
    collaborates_with: list[str] = Field(default_factory=list)
    multi_role_members: list[PositiveId] = Field(default_factory=list)

    @field_validator("team_id", "team_name", "reports_to", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        return _nonblank(value, "organization team text")

    @field_validator("primary_roles", "secondary_roles", mode="before")
    @classmethod
    def normalize_roles(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized = [
            _normalized_code(item, "organization role") for item in value
        ]
        _ensure_unique(normalized, "organization roles")
        return normalized

    @field_validator("collaborates_with", mode="before")
    @classmethod
    def normalize_team_references(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized = [
            _nonblank(item, "collaborates_with") for item in value
        ]
        _ensure_unique(normalized, "collaborates_with")
        return normalized

    @model_validator(mode="after")
    def validate_team(self) -> "OrganizationTeam":
        _ensure_unique(self.member_ids, "member_ids")
        _ensure_unique(self.assigned_wbs_ids, "assigned_wbs_ids")
        _ensure_unique(self.multi_role_members, "multi_role_members")
        if (
            self.leader_member_id is not None
            and self.leader_member_id not in self.member_ids
        ):
            raise ValueError("leader_member_id must belong to the team")
        if not set(self.multi_role_members).issubset(self.member_ids):
            raise ValueError("multi_role_members must belong to the team")
        if set(self.primary_roles) & set(self.secondary_roles):
            raise ValueError("primary_roles and secondary_roles cannot overlap")
        return self


class OrganizationRoleGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_code: str
    shortage_count: int = Field(gt=0)
    wbs_ids: list[PositiveId] = Field(default_factory=list)

    @field_validator("role_code", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> str:
        return _normalized_code(value, "role_code")

    @model_validator(mode="after")
    def reject_duplicate_wbs_ids(self) -> "OrganizationRoleGap":
        _ensure_unique(self.wbs_ids, "role gap wbs_ids")
        return self


class OrganizationView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: PositiveId
    project_manager: PositiveId | None = None
    teams: list[OrganizationTeam] = Field(default_factory=list)
    role_gaps: list[OrganizationRoleGap] = Field(default_factory=list)
    unassigned_wbs_ids: list[PositiveId] = Field(default_factory=list)
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_references(self) -> "OrganizationView":
        team_ids = [team.team_id for team in self.teams]
        _ensure_unique(team_ids, "team_ids")
        _ensure_unique(
            [gap.role_code for gap in self.role_gaps],
            "role gap role codes",
        )
        _ensure_unique(self.unassigned_wbs_ids, "unassigned_wbs_ids")
        known_team_ids = set(team_ids)
        for team in self.teams:
            if team.reports_to == team.team_id:
                raise ValueError("a team cannot report to itself")
            if team.reports_to is not None and team.reports_to not in known_team_ids:
                raise ValueError("reports_to must reference an existing team")
            unknown_collaborators = (
                set(team.collaborates_with) - known_team_ids
            )
            if unknown_collaborators:
                raise ValueError(
                    "collaborates_with must reference existing teams"
                )
            if team.team_id in team.collaborates_with:
                raise ValueError("a team cannot collaborate with itself")

        reports_to_by_team = {
            team.team_id: team.reports_to for team in self.teams
        }
        for team_id in known_team_ids:
            path = {team_id}
            current = team_id
            while reports_to_by_team[current] is not None:
                current = reports_to_by_team[current]
                if current in path:
                    raise ValueError("reports_to relationships cannot form cycles")
                path.add(current)
        return self


class KanbanStatus(str, Enum):
    BACKLOG = "BACKLOG"
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"
    DONE = "DONE"


class KanbanPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class KanbanCardMetadata(BaseModel):
    """Optional card facts which are not part of ``ResourceWBSTask``.

    BACKLOG is the documented neutral default when no workflow state is
    supplied.  Priority remains ``None`` and dependencies remain empty unless
    the caller explicitly supplies them.
    """

    model_config = ConfigDict(extra="forbid")

    wbs_id: PositiveId
    status: KanbanStatus = KanbanStatus.BACKLOG
    priority: KanbanPriority | None = None
    dependencies: list[PositiveId] = Field(default_factory=list)
    owner_member_id: PositiveId | None = None
    contributor_member_ids: list[PositiveId] = Field(default_factory=list)
    reviewer_member_ids: list[PositiveId] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)

    @field_validator(
        "risk_flags",
        "completion_criteria",
        "deliverables",
        mode="before",
    )
    @classmethod
    def normalize_descriptive_lists(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return _normalize_text_list(value, "card metadata")

    @model_validator(mode="after")
    def validate_references(self) -> "KanbanCardMetadata":
        _ensure_unique(self.dependencies, "dependencies")
        _ensure_unique(
            self.contributor_member_ids,
            "contributor_member_ids",
        )
        _ensure_unique(self.reviewer_member_ids, "reviewer_member_ids")
        if self.wbs_id in self.dependencies:
            raise ValueError("a card cannot depend on itself")
        if (
            self.owner_member_id is not None
            and self.owner_member_id in self.contributor_member_ids
        ):
            raise ValueError("owner cannot also be a contributor")
        return self


class KanbanCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wbs_id: PositiveId
    wbs_name: str
    description: str
    assigned_member_ids: list[PositiveId] = Field(default_factory=list)
    owner_member_id: PositiveId | None = None
    contributor_member_ids: list[PositiveId] = Field(default_factory=list)
    reviewer_member_ids: list[PositiveId] = Field(default_factory=list)
    start_date: date
    end_date: date
    estimated_hours: float | None = Field(default=None, gt=0)
    dependencies: list[PositiveId] = Field(default_factory=list)
    status: KanbanStatus = KanbanStatus.BACKLOG
    priority: KanbanPriority | None = None
    risk_flags: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)

    @field_validator("wbs_name", "description", mode="before")
    @classmethod
    def normalize_task_text(cls, value: object) -> str:
        return _nonblank(value, "WBS text")

    @field_validator(
        "risk_flags",
        "completion_criteria",
        "deliverables",
        mode="before",
    )
    @classmethod
    def normalize_descriptive_lists(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return _normalize_text_list(value, "card details")

    @model_validator(mode="after")
    def validate_card(self) -> "KanbanCard":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        _ensure_unique(self.dependencies, "dependencies")
        _ensure_unique(self.assigned_member_ids, "assigned_member_ids")
        _ensure_unique(
            self.contributor_member_ids,
            "contributor_member_ids",
        )
        _ensure_unique(self.reviewer_member_ids, "reviewer_member_ids")
        if self.wbs_id in self.dependencies:
            raise ValueError("a card cannot depend on itself")
        if (
            self.owner_member_id is not None
            and self.owner_member_id not in self.assigned_member_ids
        ):
            raise ValueError("owner must be an assigned member")
        if not set(self.contributor_member_ids).issubset(
            self.assigned_member_ids
        ):
            raise ValueError("contributors must be assigned members")
        if (
            self.owner_member_id is not None
            and self.owner_member_id in self.contributor_member_ids
        ):
            raise ValueError("owner cannot also be a contributor")
        return self


class KanbanBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: PositiveId
    cards: list[KanbanCard] = Field(default_factory=list)
    unassigned_wbs_ids: list[PositiveId] = Field(default_factory=list)
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_board(self) -> "KanbanBoard":
        wbs_ids = [card.wbs_id for card in self.cards]
        _ensure_unique(wbs_ids, "Kanban wbs_ids")
        _ensure_unique(self.unassigned_wbs_ids, "unassigned_wbs_ids")
        known_wbs_ids = set(wbs_ids)
        if not set(self.unassigned_wbs_ids).issubset(known_wbs_ids):
            raise ValueError("unassigned_wbs_ids must reference board cards")
        for card in self.cards:
            if not set(card.dependencies).issubset(known_wbs_ids):
                raise ValueError("dependencies must reference existing WBS cards")
        return self


class GanttTaskMetadata(BaseModel):
    """Explicit Gantt-only facts; absent facts use neutral values."""

    model_config = ConfigDict(extra="forbid")

    wbs_id: PositiveId
    progress: float = Field(default=0, ge=0, le=100)
    dependencies: list[PositiveId] = Field(default_factory=list)
    milestone: bool = False
    critical_path: bool = False

    @model_validator(mode="after")
    def validate_dependencies(self) -> "GanttTaskMetadata":
        _ensure_unique(self.dependencies, "dependencies")
        if self.wbs_id in self.dependencies:
            raise ValueError("a task cannot depend on itself")
        return self


class GanttTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: PositiveId
    task_name: str
    start_date: date
    end_date: date
    progress: float = Field(ge=0, le=100)
    dependencies: list[PositiveId] = Field(default_factory=list)
    assignee_member_ids: list[PositiveId] = Field(default_factory=list)
    milestone: bool = False
    critical_path: bool = False

    @field_validator("task_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return _nonblank(value, "task_name")

    @model_validator(mode="after")
    def validate_task(self) -> "GanttTask":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        _ensure_unique(self.dependencies, "dependencies")
        _ensure_unique(self.assignee_member_ids, "assignee_member_ids")
        if self.task_id in self.dependencies:
            raise ValueError("a task cannot depend on itself")
        return self


class GanttChart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: PositiveId
    tasks: list[GanttTask] = Field(default_factory=list)
    unassigned_wbs_ids: list[PositiveId] = Field(default_factory=list)
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_chart(self) -> "GanttChart":
        task_ids = [task.task_id for task in self.tasks]
        _ensure_unique(task_ids, "Gantt task_ids")
        _ensure_unique(self.unassigned_wbs_ids, "unassigned_wbs_ids")
        known_task_ids = set(task_ids)
        if not set(self.unassigned_wbs_ids).issubset(known_task_ids):
            raise ValueError("unassigned_wbs_ids must reference Gantt tasks")
        for task in self.tasks:
            if not set(task.dependencies).issubset(known_task_ids):
                raise ValueError(
                    "dependencies must reference existing Gantt tasks"
                )
        return self


class ScreenComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: str
    component_type: str
    label: str | None = None
    properties: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator(
        "component_id",
        "component_type",
        "label",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        return _nonblank(value, "screen component text")


class ScreenTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger: str
    target_screen_id: str
    condition: str | None = None

    @field_validator("trigger", "target_screen_id", "condition", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        return _nonblank(value, "screen transition text")


class ScreenApiBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_id: str
    method: str
    path: str
    purpose: str | None = None

    @field_validator("binding_id", "path", "purpose", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        return _nonblank(value, "API binding text")

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: object) -> str:
        return _normalized_code(value, "method")


class ScreenDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen_id: str
    screen_name: str
    purpose: str
    actors: list[str] = Field(default_factory=list)
    components: list[ScreenComponent] = Field(default_factory=list)
    transitions: list[ScreenTransition] = Field(default_factory=list)
    api_bindings: list[ScreenApiBinding] = Field(default_factory=list)
    responsive_requirements: list[str] = Field(default_factory=list)
    accessibility_requirements: list[str] = Field(default_factory=list)

    @field_validator("screen_id", "screen_name", "purpose", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return _nonblank(value, "screen text")

    @field_validator(
        "actors",
        "responsive_requirements",
        "accessibility_requirements",
        mode="before",
    )
    @classmethod
    def normalize_text_lists(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return _normalize_text_list(value, "screen details")

    @model_validator(mode="after")
    def reject_duplicate_details(self) -> "ScreenDefinition":
        _ensure_unique(
            [component.component_id for component in self.components],
            "component_ids",
        )
        _ensure_unique(
            [binding.binding_id for binding in self.api_bindings],
            "API binding_ids",
        )
        transition_keys = [
            (
                transition.trigger,
                transition.target_screen_id,
                transition.condition,
            )
            for transition in self.transitions
        ]
        _ensure_unique(transition_keys, "screen transitions")
        return self


class _ScreenSpecificationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ui_required: bool
    reason: str | None = None
    screens: list[ScreenDefinition] = Field(default_factory=list)
    allow_self_transitions: bool = False

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if value is None:
            return None
        return _nonblank(value, "reason")

    @model_validator(mode="after")
    def validate_screen_references(self) -> "_ScreenSpecificationBase":
        if not self.ui_required and self.screens:
            raise ValueError("screens must be empty when ui_required is false")
        if self.ui_required and not self.screens:
            raise ValueError(
                "at least one screen is required when ui_required is true"
            )

        screen_ids = [screen.screen_id for screen in self.screens]
        _ensure_unique(screen_ids, "screen_ids")
        known_screen_ids = set(screen_ids)
        for screen in self.screens:
            for transition in screen.transitions:
                if transition.target_screen_id not in known_screen_ids:
                    raise ValueError(
                        "transition target must reference an existing screen"
                    )
                if (
                    not self.allow_self_transitions
                    and transition.target_screen_id == screen.screen_id
                ):
                    raise ValueError(
                        "self transitions are disabled by policy"
                    )
        return self


class ScreenSpecificationInput(_ScreenSpecificationBase):
    """Fully structured caller input for the screen builder."""


class ScreenSpecification(_ScreenSpecificationBase):
    generated_at: AwareDatetime
