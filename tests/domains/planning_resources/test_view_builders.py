from __future__ import annotations

import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone

from pydantic import ValidationError

from app.domains.planning_resources.llm_service import (
    GeneratedRequiredSkill,
    GeneratedResourcePlan,
    GeneratedTaskResourceEstimate,
)
from app.domains.planning_resources.schemas import (
    PlanningResourceRequest,
    PlanningResourceResponse,
)
from app.domains.planning_resources.service import PlanningResourceService
from app.domains.planning_resources.view_builders import (
    build_gantt_chart,
    build_kanban_board,
    build_organization_chart,
    build_screen_specification,
)
from app.domains.planning_resources.view_models import (
    GanttTask,
    GanttTaskMetadata,
    KanbanCard,
    KanbanCardMetadata,
    KanbanStatus,
    OrganizationMetadata,
    OrganizationTeam,
    OrganizationView,
    ScreenSpecificationInput,
)


FIXED_GENERATED_AT = datetime(2026, 8, 3, 6, 0, tzinfo=timezone.utc)


def request_payload() -> dict:
    return {
        "project_id": 101,
        "wbs_tasks": [
            {
                "wbs_id": 3,
                "wbs_name": "결제 API 구현",
                "description": "PG사 결제 승인 및 실패 처리 API를 구현한다.",
                "start_date": "2026-08-10",
                "end_date": "2026-08-17",
            },
            {
                "wbs_id": 4,
                "wbs_name": "결제 내역 화면 개발",
                "description": (
                    "사용자별 결제 내역 조회 화면과 필터 기능을 개발한다."
                ),
                "start_date": "2026-08-18",
                "end_date": "2026-08-24",
            },
        ],
        "project_members": [
            {
                "project_member_id": 1,
                "roles": ["BACKEND"],
                "skills": [
                    {
                        "skill_code": "JAVA",
                        "proficiency_level": 4,
                        "experience_months": 36,
                    },
                    {
                        "skill_code": "SPRING_BOOT",
                        "proficiency_level": 4,
                        "experience_months": 30,
                    }
                ],
                "allocations": [
                    {
                        "allocation_start_date": "2026-08-10",
                        "allocation_end_date": "2026-08-24",
                        "available_hours_per_week": 32,
                        "allocation_status": "ACTIVE",
                    }
                ],
            },
            {
                "project_member_id": 2,
                "roles": ["FRONTEND"],
                "skills": [
                    {
                        "skill_code": "REACT",
                        "proficiency_level": 3,
                        "experience_months": 24,
                    },
                    {
                        "skill_code": "TYPESCRIPT",
                        "proficiency_level": 3,
                        "experience_months": 20,
                    }
                ],
                "allocations": [
                    {
                        "allocation_start_date": "2026-08-10",
                        "allocation_end_date": "2026-08-24",
                        "available_hours_per_week": 24,
                        "allocation_status": "ACTIVE",
                    }
                ],
            },
        ],
    }


def response_payload() -> dict:
    return {
        "project_id": 101,
        "required_staffing": [
            {
                "role_code": "BACKEND",
                "required_headcount": 1,
                "available_candidate_count": 1,
                "shortage_count": 0,
                "estimated_person_days": 2,
                "estimated_mm": 0.1,
            },
            {
                "role_code": "FRONTEND",
                "required_headcount": 2,
                "available_candidate_count": 1,
                "shortage_count": 1,
                "estimated_person_days": 2,
                "estimated_mm": 0.1,
            },
        ],
        "assignments": [
            {
                "wbs_id": 3,
                "required_role_code": "BACKEND",
                "required_skills": [
                    {
                        "skill_code": "JAVA",
                        "minimum_proficiency_level": 3,
                    }
                ],
                "estimated_person_days": 2,
                "estimated_hours": 16,
                "estimated_mm": 0.1,
                "required_headcount": 1,
                "recommended_members": [
                    {
                        "project_member_id": 1,
                        "recommendation_score": 95,
                        "assigned_hours": 16,
                        "remaining_available_hours": 16,
                    }
                ],
                "recommendation_reason": "Qualified backend member",
            },
            {
                "wbs_id": 4,
                "required_role_code": "FRONTEND",
                "required_skills": [
                    {
                        "skill_code": "REACT",
                        "minimum_proficiency_level": 3,
                    }
                ],
                "estimated_person_days": 2,
                "estimated_hours": 16,
                "estimated_mm": 0.1,
                "required_headcount": 2,
                "recommended_members": [
                    {
                        "project_member_id": 2,
                        "recommendation_score": 88,
                        "assigned_hours": 12,
                        "remaining_available_hours": 0,
                    }
                ],
                "recommendation_reason": "Partially staffed frontend work",
            },
        ],
        "total_estimated_person_days": 4,
        "total_estimated_hours": 32,
        "total_estimated_mm": 0.2,
        # WBS 4 is partially staffed, not wholly without a recommendation.
        "unassigned_wbs_ids": [4],
        "warnings": ["WBS 4 has an uncovered capacity shortfall"],
        "llm_status": "SUCCEEDED",
    }


def screen_payload() -> dict:
    return {
        "ui_required": True,
        "reason": "Payment history needs a user interface",
        "screens": [
            {
                "screen_id": "payment-list",
                "screen_name": "Payment history",
                "purpose": "List the current user's payments",
                "actors": ["CUSTOMER"],
                "components": [
                    {
                        "component_id": "history-table",
                        "component_type": "DATA_TABLE",
                        "label": "Payment history",
                    }
                ],
                "transitions": [
                    {
                        "trigger": "SELECT_PAYMENT",
                        "target_screen_id": "payment-detail",
                    }
                ],
                "api_bindings": [
                    {
                        "binding_id": "load-payments",
                        "method": "GET",
                        "path": "/api/payments",
                        "purpose": "Load payment history",
                    }
                ],
                "responsive_requirements": ["Support narrow screens"],
                "accessibility_requirements": [
                    "Expose table headers to assistive technology"
                ],
            },
            {
                "screen_id": "payment-detail",
                "screen_name": "Payment detail",
                "purpose": "Show one selected payment",
                "actors": ["CUSTOMER"],
                "components": [],
                "transitions": [],
                "api_bindings": [],
                "responsive_requirements": [],
                "accessibility_requirements": [],
            },
        ],
    }


class ViewBuilderTestCase(unittest.TestCase):
    def setUp(self):
        self.request = PlanningResourceRequest.model_validate(request_payload())
        self.response = PlanningResourceResponse.model_validate(
            response_payload()
        )

    def assert_json_serializable(self, value) -> None:
        parsed = json.loads(value.model_dump_json())
        self.assertIsInstance(parsed, dict)

    def test_organization_uses_real_ids_and_authoritative_role_gaps(self):
        request_before = self.request.model_dump(mode="json")
        response_before = self.response.model_dump(mode="json")

        result = build_organization_chart(
            self.request,
            self.response,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual(result.project_id, 101)
        self.assertIsNone(result.project_manager)
        self.assertEqual(
            [team.team_id for team in result.teams],
            ["team:101:BACKEND", "team:101:FRONTEND"],
        )
        self.assertEqual(
            [team.member_ids for team in result.teams], [[1], [2]]
        )
        self.assertEqual(
            [team.assigned_wbs_ids for team in result.teams], [[3], [4]]
        )
        self.assertTrue(
            all(
                team.leader_member_id is None
                and team.reports_to is None
                and team.collaborates_with == []
                for team in result.teams
            )
        )
        self.assertEqual(result.teams[0].multi_role_members, [])
        self.assertEqual(
            [gap.model_dump() for gap in result.role_gaps],
            [
                {
                    "role_code": "FRONTEND",
                    "shortage_count": 1,
                    "wbs_ids": [],
                }
            ],
        )
        self.assertEqual(result.unassigned_wbs_ids, [4])
        self.assertEqual(self.request.model_dump(mode="json"), request_before)
        self.assertEqual(self.response.model_dump(mode="json"), response_before)
        self.assert_json_serializable(result)

    def test_organization_marks_explicit_multi_role_members(self):
        payload = request_payload()
        payload["project_members"][0]["roles"].append("TECH_LEAD")
        request = PlanningResourceRequest.model_validate(payload)

        result = build_organization_chart(
            request,
            self.response,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual(result.teams[0].multi_role_members, [1])

    def test_organization_does_not_mark_unstaffed_wbs_as_assigned(self):
        payload = response_payload()
        payload["assignments"][1]["recommended_members"] = []

        result = build_organization_chart(
            self.request,
            payload,
            generated_at=FIXED_GENERATED_AT,
        )

        frontend_team = next(
            team for team in result.teams if team.primary_roles == ["FRONTEND"]
        )
        self.assertEqual(frontend_team.member_ids, [])
        self.assertEqual(frontend_team.assigned_wbs_ids, [])
        self.assertIn(4, result.unassigned_wbs_ids)

    def test_organization_only_uses_explicit_management_relationships(self):
        metadata = OrganizationMetadata.model_validate(
            {
                "project_manager_member_id": 1,
                "teams": [
                    {
                        "role_code": "BACKEND",
                        "team_name": "API team",
                        "leader_member_id": 1,
                        "collaborates_with_role_codes": ["FRONTEND"],
                    },
                    {
                        "role_code": "FRONTEND",
                        "reports_to_role_code": "BACKEND",
                    },
                ],
            }
        )
        metadata_before = metadata.model_dump(mode="json")

        result = build_organization_chart(
            self.request,
            self.response,
            metadata=metadata,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual(result.project_manager, 1)
        self.assertEqual(result.teams[0].team_name, "API team")
        self.assertEqual(result.teams[0].leader_member_id, 1)
        self.assertEqual(
            result.teams[0].collaborates_with, ["team:101:FRONTEND"]
        )
        self.assertEqual(result.teams[1].reports_to, "team:101:BACKEND")
        self.assertEqual(metadata.model_dump(mode="json"), metadata_before)

    def test_organization_rejects_unknown_pm_leader_role_and_relationship(self):
        invalid_metadata = (
            {"project_manager_member_id": 999},
            {
                "teams": [
                    {"role_code": "BACKEND", "leader_member_id": 2}
                ]
            },
            {"teams": [{"role_code": "QA"}]},
            {
                "teams": [
                    {
                        "role_code": "BACKEND",
                        "reports_to_role_code": "QA",
                    }
                ]
            },
            {
                "teams": [
                    {
                        "role_code": "BACKEND",
                        "reports_to_role_code": "FRONTEND",
                    },
                    {
                        "role_code": "FRONTEND",
                        "reports_to_role_code": "BACKEND",
                    },
                ]
            },
        )
        for metadata in invalid_metadata:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                build_organization_chart(
                    self.request,
                    self.response,
                    metadata=metadata,
                    generated_at=FIXED_GENERATED_AT,
                )

        with self.assertRaises(ValidationError):
            OrganizationView(
                project_id=101,
                teams=[
                    OrganizationTeam(
                        team_id="team:101:BACKEND",
                        team_name="BACKEND",
                        reports_to="team:101:BACKEND",
                    )
                ],
            )

    def test_kanban_preserves_wbs_contract_and_partial_assignment(self):
        metadata = [
            KanbanCardMetadata(
                wbs_id=4,
                status="IN_PROGRESS",
                priority="HIGH",
                dependencies=[3],
                owner_member_id=2,
                reviewer_member_ids=[1],
                risk_flags=["Capacity shortfall"],
                completion_criteria=["History can be filtered"],
                deliverables=["Payment history UI"],
            )
        ]
        request_before = self.request.model_dump(mode="json")
        response_before = self.response.model_dump(mode="json")
        metadata_before = [item.model_dump(mode="json") for item in metadata]

        result = build_kanban_board(
            self.request,
            self.response,
            metadata=metadata,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual([card.wbs_id for card in result.cards], [3, 4])
        self.assertEqual(
            [card.wbs_name for card in result.cards],
            [
                "결제 API 구현",
                "결제 내역 화면 개발",
            ],
        )
        self.assertTrue(all(card.wbs_name for card in result.cards))
        self.assertEqual(result.cards[0].assigned_member_ids, [1])
        self.assertIsNone(result.cards[0].owner_member_id)
        self.assertEqual(result.cards[0].contributor_member_ids, [])
        self.assertEqual(result.cards[0].status, KanbanStatus.BACKLOG)
        self.assertIsNone(result.cards[0].priority)
        self.assertEqual(result.cards[0].dependencies, [])
        # A partial capacity shortfall does not erase its recommendation.
        self.assertEqual(result.cards[1].assigned_member_ids, [2])
        self.assertEqual(result.cards[1].owner_member_id, 2)
        self.assertEqual(result.cards[1].estimated_hours, 16)
        self.assertEqual(result.cards[1].reviewer_member_ids, [1])
        self.assertEqual(result.unassigned_wbs_ids, [4])
        self.assertEqual(self.request.model_dump(mode="json"), request_before)
        self.assertEqual(self.response.model_dump(mode="json"), response_before)
        self.assertEqual(
            [item.model_dump(mode="json") for item in metadata],
            metadata_before,
        )
        result.cards[1].reviewer_member_ids.append(2)
        self.assertEqual(metadata[0].reviewer_member_ids, [1])
        self.assert_json_serializable(result)

    def test_gantt_preserves_wbs_contract_and_assignment(self):
        metadata = [
            GanttTaskMetadata(
                wbs_id=4,
                progress=35,
                dependencies=[3],
                milestone=True,
                critical_path=True,
            )
        ]
        metadata_before = [item.model_dump(mode="json") for item in metadata]

        result = build_gantt_chart(
            self.request,
            self.response,
            metadata=metadata,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual([task.task_id for task in result.tasks], [3, 4])
        self.assertEqual(
            [task.task_name for task in result.tasks],
            [
                "결제 API 구현",
                "결제 내역 화면 개발",
            ],
        )
        self.assertEqual(
            [(task.start_date.isoformat(), task.end_date.isoformat())
             for task in result.tasks],
            [("2026-08-10", "2026-08-17"), ("2026-08-18", "2026-08-24")],
        )
        self.assertEqual(result.tasks[0].progress, 0)
        self.assertEqual(result.tasks[0].dependencies, [])
        self.assertFalse(result.tasks[0].milestone)
        self.assertFalse(result.tasks[0].critical_path)
        self.assertEqual(result.tasks[1].assignee_member_ids, [2])
        self.assertEqual(result.tasks[1].dependencies, [3])
        self.assertEqual(result.unassigned_wbs_ids, [4])
        self.assertEqual(
            [item.model_dump(mode="json") for item in metadata],
            metadata_before,
        )
        result.tasks[1].dependencies.clear()
        self.assertEqual(metadata[0].dependencies, [3])
        self.assert_json_serializable(result)

    def test_missing_assignment_still_renders_unassigned_wbs(self):
        payload = response_payload()
        payload["assignments"] = payload["assignments"][:1]
        payload["unassigned_wbs_ids"] = [4]

        kanban = build_kanban_board(
            self.request,
            payload,
            generated_at=FIXED_GENERATED_AT,
        )
        gantt = build_gantt_chart(
            self.request,
            payload,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual([card.wbs_id for card in kanban.cards], [3, 4])
        self.assertIsNone(kanban.cards[1].owner_member_id)
        self.assertEqual(kanban.cards[1].assigned_member_ids, [])
        self.assertIsNone(kanban.cards[1].estimated_hours)
        self.assertEqual(gantt.tasks[1].assignee_member_ids, [])
        self.assertEqual(kanban.unassigned_wbs_ids, [4])
        self.assertEqual(gantt.unassigned_wbs_ids, [4])

    def test_contract_join_rejects_mismatch_unknown_and_duplicate_ids(self):
        cases = []

        project_mismatch = response_payload()
        project_mismatch["project_id"] = 999
        cases.append(project_mismatch)

        duplicate_assignment = response_payload()
        duplicate_assignment["assignments"].append(
            deepcopy(duplicate_assignment["assignments"][0])
        )
        cases.append(duplicate_assignment)

        unknown_assignment = response_payload()
        unknown_assignment["assignments"][0]["wbs_id"] = 999
        cases.append(unknown_assignment)

        duplicate_unassigned = response_payload()
        duplicate_unassigned["unassigned_wbs_ids"] = [4, 4]
        cases.append(duplicate_unassigned)

        unknown_unassigned = response_payload()
        unknown_unassigned["unassigned_wbs_ids"] = [999]
        cases.append(unknown_unassigned)

        duplicate_recommendation = response_payload()
        duplicate_recommendation["assignments"][0][
            "recommended_members"
        ].append(
            deepcopy(
                duplicate_recommendation["assignments"][0][
                    "recommended_members"
                ][0]
            )
        )
        cases.append(duplicate_recommendation)

        unknown_recommendation = response_payload()
        unknown_recommendation["assignments"][0]["recommended_members"][0][
            "project_member_id"
        ] = 999
        cases.append(unknown_recommendation)

        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                build_kanban_board(
                    self.request,
                    payload,
                    generated_at=FIXED_GENERATED_AT,
                )

    def test_kanban_validation_rejects_status_dates_and_dependencies(self):
        with self.assertRaises(ValidationError):
            KanbanCardMetadata(wbs_id=3, status="INVALID")
        with self.assertRaises(ValidationError):
            KanbanCard.model_validate(
                {
                    "wbs_id": 3,
                    "wbs_name": "Task",
                    "description": "Task description",
                    "start_date": "2026-08-17",
                    "end_date": "2026-08-10",
                }
            )
        for dependencies in ([3], [4, 4]):
            with self.subTest(dependencies=dependencies), self.assertRaises(
                ValidationError
            ):
                KanbanCardMetadata(
                    wbs_id=3,
                    dependencies=dependencies,
                )
        with self.assertRaises(ValidationError):
            build_kanban_board(
                self.request,
                self.response,
                metadata=[{"wbs_id": 3, "dependencies": [999]}],
                generated_at=FIXED_GENERATED_AT,
            )

    def test_kanban_rejects_unknown_reviewers_and_metadata_wbs(self):
        for metadata in (
            [{"wbs_id": 3, "reviewer_member_ids": [999]}],
            [{"wbs_id": 3, "owner_member_id": 999}],
            [{"wbs_id": 3, "contributor_member_ids": [999]}],
            [{"wbs_id": 3, "owner_member_id": 2}],
            [{"wbs_id": 3, "contributor_member_ids": [2]}],
            [{"wbs_id": 999}],
            [{"wbs_id": 3}, {"wbs_id": 3}],
        ):
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                build_kanban_board(
                    self.request,
                    self.response,
                    metadata=metadata,
                    generated_at=FIXED_GENERATED_AT,
                )

    def test_kanban_does_not_invent_assignment_roles(self):
        payload = response_payload()
        payload["assignments"][0]["recommended_members"].append(
            {
                "project_member_id": 2,
                "recommendation_score": 80,
                "assigned_hours": 4,
                "remaining_available_hours": 0,
            }
        )

        result = build_kanban_board(
            self.request,
            payload,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual(result.cards[0].assigned_member_ids, [1, 2])
        self.assertIsNone(result.cards[0].owner_member_id)
        self.assertEqual(result.cards[0].contributor_member_ids, [])

    def test_gantt_validation_rejects_progress_dates_and_dependencies(self):
        for progress in (-1, 101):
            with self.subTest(progress=progress), self.assertRaises(
                ValidationError
            ):
                GanttTaskMetadata(wbs_id=3, progress=progress)
        with self.assertRaises(ValidationError):
            GanttTask.model_validate(
                {
                    "task_id": 3,
                    "task_name": "Task",
                    "start_date": "2026-08-17",
                    "end_date": "2026-08-10",
                    "progress": 0,
                }
            )
        for dependencies in ([3], [4, 4]):
            with self.subTest(dependencies=dependencies), self.assertRaises(
                ValidationError
            ):
                GanttTaskMetadata(wbs_id=3, dependencies=dependencies)
        with self.assertRaises(ValidationError):
            build_gantt_chart(
                self.request,
                self.response,
                metadata=[{"wbs_id": 3, "dependencies": [999]}],
                generated_at=FIXED_GENERATED_AT,
            )

    def test_screen_specification_supports_no_ui_without_invention(self):
        screen_input = ScreenSpecificationInput(
            ui_required=False,
            reason="No user-facing workflow is required",
            screens=[],
        )
        input_before = screen_input.model_dump(mode="json")

        result = build_screen_specification(
            screen_input,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertFalse(result.ui_required)
        self.assertEqual(result.screens, [])
        self.assertNotIn("login", result.model_dump_json().lower())
        self.assertNotIn("/api/login", result.model_dump_json().lower())
        self.assertEqual(screen_input.model_dump(mode="json"), input_before)
        self.assert_json_serializable(result)

    def test_screen_specification_preserves_only_structured_input(self):
        input_data = ScreenSpecificationInput.model_validate(screen_payload())
        input_before = input_data.model_dump(mode="json")

        result = build_screen_specification(
            input_data,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual(
            [screen.screen_id for screen in result.screens],
            ["payment-list", "payment-detail"],
        )
        self.assertEqual(
            result.screens[0].transitions[0].target_screen_id,
            "payment-detail",
        )
        self.assertEqual(
            [binding.path for binding in result.screens[0].api_bindings],
            ["/api/payments"],
        )
        self.assertEqual(result.screens[1].api_bindings, [])
        self.assertEqual(input_data.model_dump(mode="json"), input_before)
        result.screens[0].components.clear()
        self.assertEqual(len(input_data.screens[0].components), 1)
        self.assert_json_serializable(result)

    def test_screen_specification_rejects_invalid_presence_and_references(self):
        one_screen = deepcopy(screen_payload()["screens"][0])
        one_screen["transitions"] = []

        invalid_payloads = [
            {
                "ui_required": False,
                "screens": [one_screen],
            },
            {"ui_required": True, "screens": []},
            {
                "ui_required": True,
                "screens": [one_screen, deepcopy(one_screen)],
            },
            {
                "ui_required": True,
                "screens": [
                    {
                        **one_screen,
                        "transitions": [
                            {
                                "trigger": "OPEN",
                                "target_screen_id": "missing-screen",
                            }
                        ],
                    }
                ],
            },
            {
                "ui_required": True,
                "screens": [
                    {
                        **one_screen,
                        "transitions": [
                            {
                                "trigger": "REFRESH",
                                "target_screen_id": one_screen["screen_id"],
                            }
                        ],
                    }
                ],
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(
                ValidationError
            ):
                build_screen_specification(
                    payload,
                    generated_at=FIXED_GENERATED_AT,
                )

    def test_screen_self_transition_can_be_enabled_explicitly(self):
        screen = deepcopy(screen_payload()["screens"][1])
        screen["transitions"] = [
            {
                "trigger": "REFRESH",
                "target_screen_id": screen["screen_id"],
            }
        ]
        result = build_screen_specification(
            {
                "ui_required": True,
                "allow_self_transitions": True,
                "screens": [screen],
            },
            generated_at=FIXED_GENERATED_AT,
        )
        self.assertEqual(
            result.screens[0].transitions[0].target_screen_id,
            screen["screen_id"],
        )

    def test_screen_allows_distinct_conditional_transitions(self):
        payload = screen_payload()
        payload["screens"][0]["transitions"].append(
            {
                "trigger": "SELECT_PAYMENT",
                "target_screen_id": "payment-detail",
                "condition": "PAYMENT_IS_SETTLED",
            }
        )

        result = build_screen_specification(
            payload,
            generated_at=FIXED_GENERATED_AT,
        )

        self.assertEqual(len(result.screens[0].transitions), 2)

    def test_fixed_generated_at_makes_builders_deterministic(self):
        first = build_kanban_board(
            self.request,
            self.response,
            generated_at=FIXED_GENERATED_AT,
        )
        second = build_kanban_board(
            self.request,
            self.response,
            generated_at=FIXED_GENERATED_AT,
        )
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_builders_require_explicit_generated_at(self):
        with self.assertRaises(TypeError):
            build_organization_chart(self.request, self.response)
        with self.assertRaises(TypeError):
            build_kanban_board(self.request, self.response)
        with self.assertRaises(TypeError):
            build_gantt_chart(self.request, self.response)
        with self.assertRaises(TypeError):
            build_screen_specification(
                {
                    "ui_required": False,
                    "reason": "UI is outside this planning request",
                    "screens": [],
                }
            )

    def test_real_contract_flow_uses_official_recommendation_and_wbs_names(self):
        """Exercise the production contracts without making a live LLM call."""

        service = PlanningResourceService()
        contexts = service.prepare_contexts(self.request)
        self.assertEqual(
            [task["wbs_id"] for task in contexts[0]["tasks"]], [3, 4]
        )
        self.assertEqual(
            [task["wbs_name"] for task in contexts[0]["tasks"]],
            [
                "결제 API 구현",
                "결제 내역 화면 개발",
            ],
        )

        # This typed plan replaces only the live model-generation segment.  The
        # official service performs all qualification, scoring, capacity, and
        # assignment calculations below.
        live_llm_status = "NOT_EXECUTED"
        plans = [
            GeneratedResourcePlan(
                task_estimates=[
                    GeneratedTaskResourceEstimate(
                        wbs_id=3,
                        required_role_code="BACKEND",
                        required_skills=[
                            GeneratedRequiredSkill(
                                skill_code="JAVA",
                                minimum_proficiency_level=3,
                            )
                        ],
                        estimated_person_days=2,
                        estimation_reason="Backend API implementation",
                    ),
                    GeneratedTaskResourceEstimate(
                        wbs_id=4,
                        required_role_code="FRONTEND",
                        required_skills=[
                            GeneratedRequiredSkill(
                                skill_code="REACT",
                                minimum_proficiency_level=3,
                            )
                        ],
                        estimated_person_days=2,
                        estimation_reason="Frontend screen implementation",
                    ),
                ]
            )
        ]
        raw_response = {
            **service.build_recommendation(self.request, plans),
            "llm_status": "SUCCEEDED",
        }
        typed_response = PlanningResourceResponse.model_validate(raw_response)

        organization = build_organization_chart(
            self.request,
            typed_response,
            generated_at=FIXED_GENERATED_AT,
        )
        kanban = build_kanban_board(
            self.request,
            raw_response,
            generated_at=FIXED_GENERATED_AT,
        )
        gantt = build_gantt_chart(
            self.request,
            typed_response,
            generated_at=FIXED_GENERATED_AT,
        )
        screen = build_screen_specification(
            {
                "ui_required": False,
                "reason": "UI specification was not requested in this flow",
                "screens": [],
            },
            generated_at=FIXED_GENERATED_AT,
        )

        input_wbs_ids = [task.wbs_id for task in self.request.wbs_tasks]
        input_wbs_names = [task.wbs_name for task in self.request.wbs_tasks]
        self.assertEqual(input_wbs_ids, [3, 4])
        self.assertEqual(
            [card.wbs_id for card in kanban.cards], input_wbs_ids
        )
        self.assertEqual(
            [task.task_id for task in gantt.tasks], input_wbs_ids
        )
        self.assertEqual(
            [card.wbs_name for card in kanban.cards], input_wbs_names
        )
        self.assertEqual(
            [task.task_name for task in gantt.tasks], input_wbs_names
        )
        output_member_ids = {
            member_id
            for team in organization.teams
            for member_id in team.member_ids
        }
        self.assertTrue(output_member_ids.issubset({1, 2}))
        self.assertEqual(live_llm_status, "NOT_EXECUTED")
        self.assertEqual(screen.screens, [])


if __name__ == "__main__":
    unittest.main()
