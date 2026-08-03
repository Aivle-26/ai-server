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


def _team_id(project_id: int, role_code: str) -> str:
    """Create a stable boundary key solely from real project/role values."""

    return f"team:{project_id}:{role_code}"


def build_organization_chart(
    request: PlanningResourceRequest,
    response: ResponseInput,
    *,
    generated_at: datetime,
    metadata: OrganizationMetadata | Mapping[str, Any] | None = None,
) -> OrganizationView:
    """Build an organization view from assignments and optional facts.

    A project manager, team leaders, reporting lines, and collaboration links
    are never inferred.  They remain empty unless supplied in ``metadata``.
    Teams are grouped by each assignment's real ``required_role_code``.
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
    wbs_ids_by_role: dict[str, list[int]] = {}
    member_ids_by_role: dict[str, list[int]] = {}
    for assignment in context.response.assignments:
        role_code = _normalize_role_code(assignment.required_role_code)
        if role_code not in wbs_ids_by_role:
            role_order.append(role_code)
            wbs_ids_by_role[role_code] = []
            member_ids_by_role[role_code] = []
        if assignment.recommended_members:
            wbs_ids_by_role[role_code].append(assignment.wbs_id)
        member_ids_by_role[role_code].extend(
            recommendation.project_member_id
            for recommendation in assignment.recommended_members
        )

    metadata_by_role = {
        item.role_code: item for item in organization_metadata.teams
    }
    unknown_metadata_roles = set(metadata_by_role) - set(role_order)
    if unknown_metadata_roles:
        raise ValueError(
            "organization team metadata must reference assignment roles"
        )

    team_id_by_role = {
        role_code: _team_id(request.project_id, role_code)
        for role_code in role_order
    }
    teams: list[OrganizationTeam] = []
    for role_code in role_order:
        team_metadata = metadata_by_role.get(role_code)
        member_ids = _unique_in_order(member_ids_by_role[role_code])
        if (
            team_metadata is not None
            and team_metadata.leader_member_id is not None
            and team_metadata.leader_member_id not in member_ids
        ):
            raise ValueError("team leader must be an assigned team member")

        reports_to = None
        collaborators: list[str] = []
        if team_metadata is not None:
            if team_metadata.reports_to_role_code is not None:
                if team_metadata.reports_to_role_code not in team_id_by_role:
                    raise ValueError(
                        "reports_to role must reference an assignment team"
                    )
                reports_to = team_id_by_role[
                    team_metadata.reports_to_role_code
                ]
            unknown_collaboration_roles = (
                set(team_metadata.collaborates_with_role_codes)
                - set(team_id_by_role)
            )
            if unknown_collaboration_roles:
                raise ValueError(
                    "collaboration roles must reference assignment teams"
                )
            collaborators = [
                team_id_by_role[collaborator_role]
                for collaborator_role in (
                    team_metadata.collaborates_with_role_codes
                )
            ]

        multi_role_members = [
            member_id
            for member_id in member_ids
            if len(context.member_by_id[member_id].roles) > 1
        ]
        teams.append(
            OrganizationTeam(
                team_id=team_id_by_role[role_code],
                team_name=(
                    team_metadata.team_name
                    if team_metadata is not None
                    and team_metadata.team_name is not None
                    else role_code
                ),
                leader_member_id=(
                    team_metadata.leader_member_id
                    if team_metadata is not None
                    else None
                ),
                member_ids=member_ids,
                primary_roles=[role_code],
                # The production member contract has no primary/secondary
                # classification, so the builder does not manufacture one.
                secondary_roles=[],
                assigned_wbs_ids=wbs_ids_by_role[role_code],
                reports_to=reports_to,
                collaborates_with=collaborators,
                multi_role_members=multi_role_members,
            )
        )

    role_gaps: list[OrganizationRoleGap] = []
    for staffing in context.required_staffing:
        if staffing.shortage_count == 0:
            continue
        role_code = _normalize_role_code(staffing.role_code)
        role_gaps.append(
            OrganizationRoleGap(
                role_code=role_code,
                shortage_count=staffing.shortage_count,
                # RequiredStaffing is role-aggregate and does not identify the
                # WBS items that caused a shortage.  Do not invent that link.
                wbs_ids=[],
            )
        )

    return OrganizationView(
        project_id=request.project_id,
        project_manager=organization_metadata.project_manager_member_id,
        teams=teams,
        role_gaps=role_gaps,
        unassigned_wbs_ids=list(context.unassigned_wbs_ids),
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
