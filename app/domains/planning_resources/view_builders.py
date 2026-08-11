"""Pure builders for planning-resource view artifacts.

The planning service currently returns a dictionary.  Every builder validates
that dictionary through :class:`PlanningResourceResponse` before reading it,
then joins it to the complete :class:`PlanningResourceRequest`.  Consequently
the builders never depend on an ad-hoc ``{wbs_id: member_id}`` mapping and can
render both partially assigned and wholly unassigned WBS tasks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .schemas import (
    PlanningResourceRequest,
    PlanningResourceResponse,
    ProjectMemberCandidate,
    RequiredStaffing,
    ResourceWBSTask,
    WBSResourceAssignment,
)
from .view_models import (
    GanttChart,
    GanttTask,
    GanttTaskMetadata,
    KanbanBoard,
    KanbanCard,
    KanbanCardMetadata,
    OrganizationMetadata,
    OrganizationRoleGap,
    OrganizationTeam,
    OrganizationView,
    ScreenSpecification,
    ScreenSpecificationInput,
)


ResponseInput = PlanningResourceResponse | Mapping[str, Any]
KanbanMetadataInput = KanbanCardMetadata | Mapping[str, Any]
GanttMetadataInput = GanttTaskMetadata | Mapping[str, Any]
ScreenInput = ScreenSpecificationInput | Mapping[str, Any]


@dataclass(frozen=True)
class _PlanningContext:
    request: PlanningResourceRequest
    response: PlanningResourceResponse
    tasks: tuple[ResourceWBSTask, ...]
    members: tuple[ProjectMemberCandidate, ...]
    assignment_by_wbs_id: dict[int, WBSResourceAssignment]
    member_by_id: dict[int, ProjectMemberCandidate]
    unassigned_wbs_ids: tuple[int, ...]
    required_staffing: tuple[RequiredStaffing, ...]


def _normalize_role_code(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("role codes must be strings")
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("role codes cannot be blank")
    return normalized


def _unique_in_order(values: Sequence[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _planning_context(
    request: PlanningResourceRequest,
    response: ResponseInput,
) -> _PlanningContext:
    """Validate the real request/response join used by every planning view.

    The response is authoritative for scores, assigned hours, and capacity
    shortfalls.  Builders verify project and reference integrity but never
    recalculate those service-owned values or duplicate the official scoring
    and allocation logic.
    """

    if not isinstance(request, PlanningResourceRequest):
        raise TypeError("request must be a PlanningResourceRequest")
    validated_response = PlanningResourceResponse.model_validate(response)
    if validated_response.project_id != request.project_id:
        raise ValueError("request and response project_id values must match")

    tasks = tuple(request.wbs_tasks)
    members = tuple(request.project_members)
    task_ids = [task.wbs_id for task in tasks]
    member_ids = [member.project_member_id for member in members]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("request contains duplicate WBS IDs")
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("request contains duplicate project member IDs")

    known_task_ids = set(task_ids)
    known_member_ids = set(member_ids)
    assignment_ids = [
        assignment.wbs_id for assignment in validated_response.assignments
    ]
    if len(assignment_ids) != len(set(assignment_ids)):
        raise ValueError("response contains duplicate WBS assignments")
    unknown_assignment_ids = set(assignment_ids) - known_task_ids
    if unknown_assignment_ids:
        raise ValueError("assignments must reference request WBS IDs")

    reported_unassigned_ids = validated_response.unassigned_wbs_ids
    if len(reported_unassigned_ids) != len(set(reported_unassigned_ids)):
        raise ValueError("response contains duplicate unassigned WBS IDs")
    if not set(reported_unassigned_ids).issubset(known_task_ids):
        raise ValueError("unassigned WBS IDs must reference request tasks")

    for assignment in validated_response.assignments:
        _normalize_role_code(assignment.required_role_code)
        recommended_ids = [
            recommendation.project_member_id
            for recommendation in assignment.recommended_members
        ]
        if len(recommended_ids) != len(set(recommended_ids)):
            raise ValueError(
                "an assignment cannot recommend the same member twice"
            )
        if not set(recommended_ids).issubset(known_member_ids):
            raise ValueError(
                "recommended members must reference request members"
            )

    staffing_roles = [
        _normalize_role_code(staffing.role_code)
        for staffing in validated_response.required_staffing
    ]
    if len(staffing_roles) != len(set(staffing_roles)):
        raise ValueError("response contains duplicate required staffing roles")

    assignment_by_wbs_id = {
        assignment.wbs_id: assignment
        for assignment in validated_response.assignments
    }
    missing_assignment_ids = [
        task_id for task_id in task_ids if task_id not in assignment_by_wbs_id
    ]
    assignments_without_members = [
        assignment.wbs_id
        for assignment in validated_response.assignments
        if not assignment.recommended_members
    ]
    unassigned_set = {
        *reported_unassigned_ids,
        *missing_assignment_ids,
        *assignments_without_members,
    }
    ordered_unassigned_ids = tuple(
        task_id for task_id in task_ids if task_id in unassigned_set
    )

    return _PlanningContext(
        request=request,
        response=validated_response,
        tasks=tasks,
        members=members,
        assignment_by_wbs_id=assignment_by_wbs_id,
        member_by_id={member.project_member_id: member for member in members},
        unassigned_wbs_ids=ordered_unassigned_ids,
        required_staffing=tuple(validated_response.required_staffing),
    )


def _member_team_id(project_id: int, member_id: int) -> str:
    """Create a stable organization-node key from a real project member."""

    return f"member:{project_id}:{member_id}"


def _project_manager_member_id(
    members: Sequence[ProjectMemberCandidate],
    metadata: OrganizationMetadata,
) -> int | None:
    if metadata.project_manager_member_id is not None:
        return metadata.project_manager_member_id
    for member in members:
        if any(role in {"PM", "PROJECT_MANAGER"} for role in member.roles):
            return member.project_member_id
    return None


def _primary_role(
    member: ProjectMemberCandidate,
    assigned_roles: Sequence[str],
    *,
    is_project_manager: bool,
) -> str | None:
    if is_project_manager:
        return next(
            (
                role
                for role in member.roles
                if role in {"PM", "PROJECT_MANAGER"}
            ),
            "PROJECT_MANAGER",
        )
    if not assigned_roles:
        return member.roles[0] if member.roles else None

    counts = {
        role: assigned_roles.count(role) for role in set(assigned_roles)
    }
    capability_order = {
        role: index for index, role in enumerate(member.roles)
    }
    assignment_order = {
        role: index for index, role in enumerate(_unique_text(assigned_roles))
    }
    return min(
        counts,
        key=lambda role: (
            -counts[role],
            capability_order.get(role, len(capability_order)),
            assignment_order[role],
        ),
    )


def _unique_text(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _validate_metadata_relationships(
    metadata_by_role: Mapping[str, Any],
    known_roles: set[str],
) -> None:
    for role_code, team_metadata in metadata_by_role.items():
        references = {
            *team_metadata.collaborates_with_role_codes,
            *(
                [team_metadata.reports_to_role_code]
                if team_metadata.reports_to_role_code is not None
                else []
            ),
        }
        if not references.issubset(known_roles):
            raise ValueError(
                "organization relationships must reference assignment roles"
            )

    reports_to_by_role = {
        role_code: team_metadata.reports_to_role_code
        for role_code, team_metadata in metadata_by_role.items()
    }
    for role_code in reports_to_by_role:
        path = {role_code}
        current = role_code
        while reports_to_by_role.get(current) is not None:
            current = reports_to_by_role[current]
            if current in path:
                raise ValueError(
                    "organization reporting relationships cannot form cycles"
                )
            path.add(current)


def build_organization_chart(
    request: PlanningResourceRequest,
    response: ResponseInput,
    *,
    generated_at: datetime,
    metadata: OrganizationMetadata | Mapping[str, Any] | None = None,
) -> OrganizationView:
    """Build an organization view from assignments and optional facts.

    Explicit metadata wins for project management and reporting facts.  When
    it is absent, only an actual member's declared PM capability may select
    the project manager; no person or relationship is synthesized.
    Each node represents one real request member.  Assignment roles determine
    the member's primary and secondary roles without creating vacant role
    nodes or synthetic people.
    """

    context = _planning_context(request, response)
    organization_metadata = (
        OrganizationMetadata()
        if metadata is None
        else OrganizationMetadata.model_validate(metadata)
    )
    if (
        organization_metadata.project_manager_member_id is not None
        and organization_metadata.project_manager_member_id
        not in context.member_by_id
    ):
        raise ValueError("project manager must reference a request member")

    role_order: list[str] = []
    member_ids_by_role: dict[str, list[int]] = {}
    roles_by_member_id: dict[int, list[str]] = {
        member.project_member_id: [] for member in context.members
    }
    wbs_ids_by_member_id: dict[int, list[int]] = {
        member.project_member_id: [] for member in context.members
    }
    for assignment in context.response.assignments:
        role_code = _normalize_role_code(assignment.required_role_code)
        if role_code not in member_ids_by_role:
            role_order.append(role_code)
            member_ids_by_role[role_code] = []
        for recommendation in assignment.recommended_members:
            member_id = recommendation.project_member_id
            member_ids_by_role[role_code].append(member_id)
            roles_by_member_id[member_id].append(role_code)
            wbs_ids_by_member_id[member_id].append(assignment.wbs_id)

    metadata_by_role = {
        item.role_code: item for item in organization_metadata.teams
    }
    unknown_metadata_roles = set(metadata_by_role) - set(role_order)
    if unknown_metadata_roles:
        raise ValueError(
            "organization team metadata must reference assignment roles"
        )
    _validate_metadata_relationships(metadata_by_role, set(role_order))

    for role_code, team_metadata in metadata_by_role.items():
        assigned_member_ids = set(member_ids_by_role[role_code])
        if (
            team_metadata.leader_member_id is not None
            and team_metadata.leader_member_id not in assigned_member_ids
        ):
            raise ValueError("team leader must be an assigned team member")

    role_representative: dict[str, int] = {}
    for role_code in role_order:
        assigned_member_ids = _unique_in_order(member_ids_by_role[role_code])
        team_metadata = metadata_by_role.get(role_code)
        if team_metadata is not None and team_metadata.leader_member_id is not None:
            role_representative[role_code] = team_metadata.leader_member_id
        elif assigned_member_ids:
            role_representative[role_code] = assigned_member_ids[0]

    project_manager = _project_manager_member_id(
        context.members,
        organization_metadata,
    )
    primary_role_by_member_id = {
        member.project_member_id: _primary_role(
            member,
            roles_by_member_id[member.project_member_id],
            is_project_manager=member.project_member_id == project_manager,
        )
        for member in context.members
    }
    lead_member_id = next(
        (
            member.project_member_id
            for member in context.members
            if member.project_member_id != project_manager
            and any(
                role in {"TECH_LEAD", "TEAM_LEAD", "DELIVERY_LEAD"}
                for role in member.roles
            )
        ),
        None,
    )
    backend_member_id = next(
        (
            member.project_member_id
            for member in context.members
            if member.project_member_id not in {project_manager, lead_member_id}
            and primary_role_by_member_id[member.project_member_id]
            in {"BACKEND", "BACKEND_DEVELOPER"}
        ),
        None,
    )
    teams: list[OrganizationTeam] = []
    for member in context.members:
        member_id = member.project_member_id
        assigned_roles = roles_by_member_id[member_id]
        primary_role = primary_role_by_member_id[member_id]
        secondary_roles = [
            role
            for role in _unique_text(assigned_roles)
            if role != primary_role
        ]
        team_metadata = next(
            (
                metadata_by_role[role]
                for role in ([primary_role] if primary_role else [])
                + secondary_roles
                if role in metadata_by_role
            ),
            None,
        )
        is_designated_leader = any(
            metadata.leader_member_id == member_id
            for metadata in metadata_by_role.values()
        )
        reports_to = None
        collaborators: list[str] = []
        if team_metadata is not None:
            if team_metadata.reports_to_role_code is not None:
                target_member_id = role_representative.get(
                    team_metadata.reports_to_role_code
                )
                if target_member_id is None:
                    raise ValueError(
                        "reports_to role must have an assigned project member"
                    )
                reports_to = _member_team_id(
                    request.project_id,
                    target_member_id,
                )
            collaborators = [
                _member_team_id(request.project_id, role_representative[role])
                for role in team_metadata.collaborates_with_role_codes
                if role in role_representative
            ]

        if (
            project_manager is not None
            and member_id != project_manager
            and reports_to is None
        ):
            parent_member_id = project_manager
            if (
                lead_member_id is not None
                and primary_role in {
                    "FULLSTACK",
                    "FULLSTACK_DEVELOPER",
                    "QA",
                    "QA_ENGINEER",
                }
            ):
                parent_member_id = lead_member_id
            elif (
                backend_member_id is not None
                and primary_role in {"FRONTEND", "FRONTEND_DEVELOPER"}
            ):
                parent_member_id = backend_member_id
            if parent_member_id is not None:
                reports_to = _member_team_id(
                    request.project_id,
                    parent_member_id,
                )

        team_id = _member_team_id(request.project_id, member_id)
        collaborators = [
            collaborator
            for collaborator in _unique_text(collaborators)
            if collaborator != team_id
        ]
        if reports_to == team_id:
            reports_to = None
        teams.append(
            OrganizationTeam(
                team_id=team_id,
                team_name=member.member_name or f"ID {member_id}",
                leader_member_id=(
                    member_id if is_designated_leader else None
                ),
                member_ids=[member_id],
                primary_roles=[primary_role] if primary_role else [],
                secondary_roles=secondary_roles,
                assigned_wbs_ids=_unique_in_order(
                    wbs_ids_by_member_id[member_id]
                ),
                reports_to=reports_to,
                collaborates_with=collaborators,
                multi_role_members=(
                    [member_id] if secondary_roles else []
                ),
            )
        )

    role_gaps: list[OrganizationRoleGap] = []
    for staffing in context.required_staffing:
        if staffing.shortage_count == 0:
            continue
        role_code = _normalize_role_code(staffing.role_code)
        role_wbs_ids = [
            wbs_id
            for wbs_id in context.unassigned_wbs_ids
            if (
                (assignment := context.assignment_by_wbs_id.get(wbs_id))
                is not None
                and _normalize_role_code(assignment.required_role_code)
                == role_code
            )
        ]
        role_gaps.append(
            OrganizationRoleGap(
                role_code=role_code,
                shortage_count=staffing.shortage_count,
                wbs_ids=role_wbs_ids,
            )
        )

    return OrganizationView(
        project_id=request.project_id,
        project_manager=project_manager,
        teams=teams,
        role_gaps=role_gaps,
        unassigned_wbs_ids=list(context.unassigned_wbs_ids),
        warnings=list(context.response.warnings),
        generated_at=generated_at,
    )


def _kanban_metadata_by_wbs_id(
    values: Sequence[KanbanMetadataInput] | None,
    known_wbs_ids: set[int],
) -> dict[int, KanbanCardMetadata]:
    metadata = [
        KanbanCardMetadata.model_validate(value) for value in values or ()
    ]
    wbs_ids = [item.wbs_id for item in metadata]
    if len(wbs_ids) != len(set(wbs_ids)):
        raise ValueError("Kanban metadata contains duplicate WBS IDs")
    if not set(wbs_ids).issubset(known_wbs_ids):
        raise ValueError("Kanban metadata must reference request WBS IDs")
    return {item.wbs_id: item for item in metadata}


def build_kanban_board(
    request: PlanningResourceRequest,
    response: ResponseInput,
    *,
    generated_at: datetime,
    metadata: Sequence[KanbanMetadataInput] | None = None,
) -> KanbanBoard:
    """Build one Kanban card for every request WBS task.

    Recommendations are preserved neutrally as ``assigned_member_ids`` because
    the production assignment contract does not label owners or contributors.
    Those roles, reviewers, and workflow-only fields are included only when
    explicitly supplied as typed metadata.
    """

    context = _planning_context(request, response)
    known_wbs_ids = {task.wbs_id for task in context.tasks}
    metadata_by_wbs_id = _kanban_metadata_by_wbs_id(
        metadata,
        known_wbs_ids,
    )

    known_member_ids = set(context.member_by_id)
    for item in metadata_by_wbs_id.values():
        referenced_member_ids = {
            *item.contributor_member_ids,
            *item.reviewer_member_ids,
        }
        if item.owner_member_id is not None:
            referenced_member_ids.add(item.owner_member_id)
        if not referenced_member_ids.issubset(known_member_ids):
            raise ValueError("card metadata must reference request members")

    cards: list[KanbanCard] = []
    for task in context.tasks:
        assignment = context.assignment_by_wbs_id.get(task.wbs_id)
        card_metadata = metadata_by_wbs_id.get(task.wbs_id)
        recommendations = (
            list(assignment.recommended_members) if assignment else []
        )
        assigned_member_ids = [
            recommendation.project_member_id
            for recommendation in recommendations
        ]
        cards.append(
            KanbanCard(
                wbs_id=task.wbs_id,
                wbs_name=task.wbs_name,
                description=task.description,
                assigned_member_ids=assigned_member_ids,
                owner_member_id=(
                    card_metadata.owner_member_id
                    if card_metadata is not None
                    else None
                ),
                contributor_member_ids=(
                    list(card_metadata.contributor_member_ids)
                    if card_metadata is not None
                    else []
                ),
                reviewer_member_ids=(
                    list(card_metadata.reviewer_member_ids)
                    if card_metadata is not None
                    else []
                ),
                start_date=task.start_date,
                end_date=task.end_date,
                estimated_hours=(
                    assignment.estimated_hours if assignment else None
                ),
                dependencies=(
                    list(card_metadata.dependencies)
                    if card_metadata is not None
                    else []
                ),
                status=(
                    card_metadata.status
                    if card_metadata is not None
                    else "BACKLOG"
                ),
                priority=(
                    card_metadata.priority
                    if card_metadata is not None
                    else None
                ),
                risk_flags=(
                    list(card_metadata.risk_flags)
                    if card_metadata is not None
                    else []
                ),
                completion_criteria=(
                    list(card_metadata.completion_criteria)
                    if card_metadata is not None
                    else []
                ),
                deliverables=(
                    list(card_metadata.deliverables)
                    if card_metadata is not None
                    else []
                ),
            )
        )

    return KanbanBoard(
        project_id=request.project_id,
        cards=cards,
        unassigned_wbs_ids=list(context.unassigned_wbs_ids),
        generated_at=generated_at,
    )


def _gantt_metadata_by_wbs_id(
    values: Sequence[GanttMetadataInput] | None,
    known_wbs_ids: set[int],
) -> dict[int, GanttTaskMetadata]:
    metadata = [
        GanttTaskMetadata.model_validate(value) for value in values or ()
    ]
    wbs_ids = [item.wbs_id for item in metadata]
    if len(wbs_ids) != len(set(wbs_ids)):
        raise ValueError("Gantt metadata contains duplicate WBS IDs")
    if not set(wbs_ids).issubset(known_wbs_ids):
        raise ValueError("Gantt metadata must reference request WBS IDs")
    return {item.wbs_id: item for item in metadata}


def build_gantt_chart(
    request: PlanningResourceRequest,
    response: ResponseInput,
    *,
    generated_at: datetime,
    metadata: Sequence[GanttMetadataInput] | None = None,
) -> GanttChart:
    """Build a Gantt view without calculating dates or dependencies.

    Dates and names are copied from ``ResourceWBSTask``.  Progress,
    dependencies, milestone, and critical-path flags use neutral defaults and
    only change through explicit typed metadata.
    """

    context = _planning_context(request, response)
    known_wbs_ids = {task.wbs_id for task in context.tasks}
    metadata_by_wbs_id = _gantt_metadata_by_wbs_id(
        metadata,
        known_wbs_ids,
    )

    tasks: list[GanttTask] = []
    for task in context.tasks:
        assignment = context.assignment_by_wbs_id.get(task.wbs_id)
        task_metadata = metadata_by_wbs_id.get(task.wbs_id)
        tasks.append(
            GanttTask(
                task_id=task.wbs_id,
                task_name=task.wbs_name,
                start_date=task.start_date,
                end_date=task.end_date,
                progress=(
                    task_metadata.progress
                    if task_metadata is not None
                    else 0
                ),
                dependencies=(
                    list(task_metadata.dependencies)
                    if task_metadata is not None
                    else []
                ),
                assignee_member_ids=(
                    [
                        recommendation.project_member_id
                        for recommendation in assignment.recommended_members
                    ]
                    if assignment is not None
                    else []
                ),
                milestone=(
                    task_metadata.milestone
                    if task_metadata is not None
                    else False
                ),
                critical_path=(
                    task_metadata.critical_path
                    if task_metadata is not None
                    else False
                ),
            )
        )

    return GanttChart(
        project_id=request.project_id,
        tasks=tasks,
        unassigned_wbs_ids=list(context.unassigned_wbs_ids),
        generated_at=generated_at,
    )


def build_screen_specification(
    screen_input: ScreenInput,
    *,
    generated_at: datetime,
) -> ScreenSpecification:
    """Validate and copy caller-supplied UI decisions into a view artifact.

    The builder never creates login screens, API routes, transitions, or Figma
    details.  Cross-screen references and the explicit self-transition policy
    are validated by ``ScreenSpecificationInput`` before conversion.
    """

    validated_input = ScreenSpecificationInput.model_validate(screen_input)
    return ScreenSpecification.model_validate(
        {
            **validated_input.model_dump(mode="python"),
            "generated_at": generated_at,
        }
    )
