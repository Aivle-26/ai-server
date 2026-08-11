from __future__ import annotations

import base64
import os
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageFont
from pydantic import ValidationError

from app.domains.planning_resources import organization_chart as chart_module
from app.domains.planning_resources.organization_chart import (
    OrganizationChartConfigurationError,
    OrganizationChartGenerationRequest,
    OrganizationChartRenderRequest,
    render_organization_chart,
)
from app.domains.planning_resources.schemas import PlanningResourceRequest
from app.domains.planning_resources.view_builders import build_organization_chart
from app.domains.planning_resources.view_models import OrganizationView
from app.main import app


GENERATED_AT = datetime(2026, 8, 11, 1, 0, tzinfo=timezone.utc)


def planning_payload() -> dict:
    return {
        "project_id": 7,
        "project_name": "한국어 서비스 프로젝트",
        "wbs_tasks": [
            {
                "wbs_id": member_id,
                "wbs_name": f"업무 {member_id}",
                "description": f"프로젝트 업무 {member_id}",
                "start_date": "2026-08-03",
                "end_date": "2026-08-14",
            }
            for member_id in range(1, 9)
        ],
        "project_members": [
            member(1, "김민성 (PM001)", ["PM"]),
            member(2, "김현우 (DEV002)", ["TECH_LEAD", "BACKEND"]),
            member(3, "이서연 (DEV003)", ["BACKEND"]),
            member(4, "박지훈 (DEV004)", ["DEVOPS"]),
            member(5, "최유진 (DEV005)", ["FULLSTACK"]),
            member(6, "정다은 (DEV006)", ["QA"]),
            member(7, "한도윤 (DEV007)", ["MOBILE"]),
            member(8, "송하늘 (DEV008)", []),
        ],
    }


def member(member_id: int, name: str, roles: list[str]) -> dict:
    return {
        "project_member_id": member_id,
        "member_name": name,
        "roles": roles,
        "skills": [],
        "allocations": [],
    }


def assignment(wbs_id: int, role: str, member_id: int | None) -> dict:
    recommendations = []
    if member_id is not None:
        recommendations.append(
            {
                "project_member_id": member_id,
                "recommendation_score": 90,
                "assigned_hours": 8,
                "remaining_available_hours": 24,
            }
        )
    return {
        "wbs_id": wbs_id,
        "required_role_code": role,
        "required_skills": [],
        "estimated_person_days": 1,
        "estimated_hours": 8,
        "estimated_mm": 0.05,
        "required_headcount": 1,
        "recommended_members": recommendations,
        "recommendation_reason": "fixture assignment",
    }


def recommendation_payload() -> dict:
    assignments = [
        assignment(1, "PM", 1),
        assignment(2, "TECH_LEAD", 2),
        assignment(3, "BACKEND", 3),
        assignment(4, "DEVOPS", 4),
        assignment(5, "FULLSTACK", 5),
        assignment(6, "QA", 6),
        assignment(7, "MOBILE", 7),
        assignment(8, "DOCUMENT_REVIEWER", None),
    ]
    return {
        "project_id": 7,
        "required_staffing": [
            {
                "role_code": "DOCUMENT_REVIEWER",
                "required_headcount": 1,
                "available_candidate_count": 0,
                "shortage_count": 1,
                "estimated_person_days": 1,
                "estimated_mm": 0.05,
            }
        ],
        "assignments": assignments,
        "total_estimated_person_days": 8,
        "total_estimated_hours": 64,
        "total_estimated_mm": 0.4,
        "unassigned_wbs_ids": [8],
        "warnings": ["역량 정보가 없어 자동 배정에서 제외된 팀원이 1명 있습니다."],
        "llm_status": "SUCCEEDED",
    }


def metadata_payload() -> dict:
    return {
        "project_manager_member_id": 1,
        "teams": [],
    }


def default_fonts() -> chart_module._Fonts:
    font_path = next(
        path
        for path in (
            Path("C:/Windows/Fonts/malgun.ttf"),
            *(Path(candidate) for candidate in chart_module._FONT_CANDIDATES),
        )
        if path.is_file()
    )
    return chart_module._Fonts(
        ImageFont.truetype(str(font_path), 34),
        ImageFont.truetype(str(font_path), 24),
        ImageFont.truetype(str(font_path), 20),
        ImageFont.truetype(str(font_path), 16),
    )


def build_view() -> tuple[PlanningResourceRequest, OrganizationView]:
    request = PlanningResourceRequest.model_validate(planning_payload())
    view = build_organization_chart(
        request,
        recommendation_payload(),
        metadata=metadata_payload(),
        generated_at=GENERATED_AT,
    )
    return request, view


def build_hierarchy_fixture_view() -> tuple[PlanningResourceRequest, OrganizationView]:
    payload = planning_payload()
    payload["project_members"][-1]["roles"] = ["FRONTEND"]
    response = recommendation_payload()
    response["assignments"][-1] = assignment(8, "FRONTEND", 8)
    response["required_staffing"] = []
    response["unassigned_wbs_ids"] = []
    response["warnings"] = []
    request = PlanningResourceRequest.model_validate(payload)
    view = build_organization_chart(
        request,
        response,
        metadata=metadata_payload(),
        generated_at=GENERATED_AT,
    )
    return request, view


def team_for(view: OrganizationView, member_id: int):
    return next(team for team in view.teams if team.member_ids == [member_id])


def move_member(
    view: OrganizationView,
    member_id: int,
    parent_member_id: int,
) -> OrganizationView:
    parent_team = team_for(view, parent_member_id)
    teams = [
        team.model_copy(update={"reports_to": parent_team.team_id})
        if team.member_ids == [member_id]
        else team
        for team in view.teams
    ]
    return OrganizationView.model_validate(
        {**view.model_dump(), "teams": [team.model_dump() for team in teams]}
    )


class FailingGraph:
    def invoke(self, request):
        raise AssertionError("manual render must not invoke allocation AI")


class FakeGraph:
    def invoke(self, request):
        return recommendation_payload()


class OrganizationChartTest(unittest.TestCase):
    def test_generation_request_accepts_existing_contract(self):
        parsed = OrganizationChartGenerationRequest.model_validate(
            {
                "planning_request": planning_payload(),
                "organization_metadata": metadata_payload(),
            }
        )
        self.assertEqual(parsed.planning_request.project_id, 7)
        self.assertEqual(parsed.organization_metadata.project_manager_member_id, 1)

    def test_default_hierarchy_uses_pm_root_and_tech_lead(self):
        _, view = build_hierarchy_fixture_view()
        pm = team_for(view, 1)
        lead = team_for(view, 2)
        backend = team_for(view, 3)
        devops = team_for(view, 4)
        fullstack = team_for(view, 5)
        qa = team_for(view, 6)
        mobile = team_for(view, 7)
        frontend = team_for(view, 8)

        self.assertIsNone(pm.reports_to)
        self.assertEqual(lead.reports_to, pm.team_id)
        self.assertEqual(backend.reports_to, pm.team_id)
        self.assertEqual(devops.reports_to, pm.team_id)
        self.assertEqual(mobile.reports_to, pm.team_id)
        self.assertEqual(fullstack.reports_to, lead.team_id)
        self.assertEqual(qa.reports_to, lead.team_id)
        self.assertEqual(frontend.reports_to, backend.team_id)
        parents = chart_module._hierarchy_parent_by_team(view)
        depths = chart_module._hierarchy_depths(parents)
        self.assertEqual(depths[pm.team_id], 0)
        self.assertEqual(depths[lead.team_id], 1)
        self.assertEqual(depths[fullstack.team_id], 2)
        self.assertEqual(depths[frontend.team_id], 2)

    def test_eight_members_remain_unique_real_and_non_synthetic(self):
        request, view = build_view()
        displayed_ids = [
            member_id for team in view.teams for member_id in team.member_ids
        ]
        input_ids = {
            candidate.project_member_id for candidate in request.project_members
        }

        self.assertEqual(len(displayed_ids), 8)
        self.assertEqual(len(set(displayed_ids)), 8)
        self.assertEqual(set(displayed_ids), input_ids)
        self.assertTrue(all(len(team.member_ids) == 1 for team in view.teams))
        self.assertFalse(any(not team.member_ids for team in view.teams))

    def test_missing_capability_member_stays_in_hierarchy_without_role_or_wbs(self):
        request, view = build_view()
        unknown = team_for(view, 8)

        self.assertEqual(unknown.primary_roles, [])
        self.assertEqual(unknown.secondary_roles, [])
        self.assertEqual(unknown.assigned_wbs_ids, [])
        self.assertEqual(unknown.reports_to, team_for(view, 1).team_id)
        labels = [
            value
            for _, value in chart_module._team_content(
                request,
                unknown,
                hierarchy_label="김현우 산하",
            )
        ]
        self.assertIn("역량 미등록", labels)
        self.assertIn("직무 미배정", labels)

        with patch.object(chart_module, "_load_fonts", default_fonts):
            rendered = render_organization_chart(request, view)
        self.assertTrue(rendered.content.startswith(b"\xff\xd8\xff"))

    def test_seven_and_four_of_eight_capabilities_keep_real_members_unassigned(self):
        for capability_count in (7, 4):
            with self.subTest(capability_count=capability_count):
                payload = planning_payload()
                unknown_ids = {
                    candidate["project_member_id"]
                    for candidate in payload["project_members"][capability_count:]
                }
                for candidate in payload["project_members"][capability_count:]:
                    candidate["roles"] = []
                response = recommendation_payload()
                for item in response["assignments"]:
                    item["recommended_members"] = [
                        candidate
                        for candidate in item["recommended_members"]
                        if candidate["project_member_id"] not in unknown_ids
                    ]
                response["unassigned_wbs_ids"] = [
                    item["wbs_id"]
                    for item in response["assignments"]
                    if not item["recommended_members"]
                ]
                response["warnings"] = [
                    "역량 정보가 없어 자동 배정에서 제외된 팀원이 "
                    f"{len(unknown_ids)}명 있습니다."
                ]
                request = PlanningResourceRequest.model_validate(payload)
                view = build_organization_chart(
                    request,
                    response,
                    metadata=metadata_payload(),
                    generated_at=GENERATED_AT,
                )

                displayed_ids = [
                    member_id for team in view.teams for member_id in team.member_ids
                ]
                unknown_teams = [
                    team for team in view.teams if team.member_ids[0] in unknown_ids
                ]
                self.assertEqual(len(displayed_ids), 8)
                self.assertEqual(len(set(displayed_ids)), 8)
                self.assertEqual(set(displayed_ids), set(range(1, 9)))
                self.assertEqual(len(unknown_teams), len(unknown_ids))
                self.assertTrue(
                    all(
                        not team.primary_roles
                        and not team.secondary_roles
                        and not team.assigned_wbs_ids
                        for team in unknown_teams
                    )
                )
                with patch.object(chart_module, "_load_fonts", default_fonts):
                    rendered = render_organization_chart(request, view)
                self.assertTrue(rendered.content.startswith(b"\xff\xd8\xff"))

    def test_card_hides_wbs_secondary_roles_and_detailed_role_gaps(self):
        request, view = build_view()
        lead = team_for(view, 2).model_copy(
            update={
                "assigned_wbs_ids": [1, 2, 3, 4],
                "secondary_roles": ["BACKEND", "QA"],
            }
        )
        labels = [
            value
            for _, value in chart_module._team_content(
                request,
                lead,
                hierarchy_label="PM 직속",
            )
        ]
        footer = chart_module._assignment_footer(view)

        self.assertFalse(any("WBS" in label for label in labels))
        self.assertFalse(any("BACKEND" in label for label in labels))
        self.assertFalse(any("QA" in label for label in labels))
        self.assertEqual(
            footer,
            "배정 요약 · 미배정 WBS 1건 · 역할 Gap 1개",
        )
        self.assertNotIn("DOCUMENT_REVIEWER", footer)

    def test_manual_move_changes_only_hierarchy(self):
        request, view = build_hierarchy_fixture_view()
        before = team_for(view, 8)
        moved = move_member(view, 8, 2)
        after = team_for(moved, 8)

        self.assertNotEqual(before.reports_to, after.reports_to)
        self.assertEqual(before.primary_roles, after.primary_roles)
        self.assertEqual(before.secondary_roles, after.secondary_roles)
        self.assertEqual(before.assigned_wbs_ids, after.assigned_wbs_ids)
        self.assertEqual(after.reports_to, team_for(moved, 2).team_id)

        with patch.object(chart_module, "_load_fonts", default_fonts):
            rendered = render_organization_chart(request, moved)
        self.assertTrue(rendered.content.startswith(b"\xff\xd8\xff"))

    def test_flat_two_depth_three_depth_and_moved_views_render_safely(self):
        request, view = build_hierarchy_fixture_view()
        pm = team_for(view, 1)
        flat = OrganizationView.model_validate(
            {
                **view.model_dump(),
                "teams": [
                    team.model_copy(
                        update={
                            "reports_to": None
                            if team.member_ids == [1]
                            else pm.team_id
                        }
                    ).model_dump()
                    for team in view.teams
                ],
            }
        )
        moved = move_member(view, 8, 2)

        with patch.object(chart_module, "_load_fonts", default_fonts):
            rendered = [
                render_organization_chart(request, candidate)
                for candidate in (flat, view, moved)
            ]
        for image in rendered:
            self.assertLessEqual(image.width, chart_module.MAX_IMAGE_WIDTH)
            self.assertLessEqual(image.height, chart_module.MAX_IMAGE_HEIGHT)
            with Image.open(BytesIO(image.content)) as opened:
                self.assertEqual(opened.format, "JPEG")

    def test_cycle_and_project_manager_parent_are_rejected(self):
        _, view = build_view()
        pm = team_for(view, 1)
        lead = team_for(view, 2)
        cycle_teams = [
            team.model_copy(update={"reports_to": lead.team_id})
            if team is pm
            else team.model_copy(update={"reports_to": pm.team_id})
            if team is lead
            else team
            for team in view.teams
        ]
        with self.assertRaises(ValidationError):
            OrganizationView.model_validate(
                {
                    **view.model_dump(),
                    "teams": [team.model_dump() for team in cycle_teams],
                }
            )

    def test_invalid_configured_font_raises_clear_error(self):
        with patch.dict(os.environ, {"ORG_CHART_FONT_PATH": "missing-font.ttc"}):
            with self.assertRaisesRegex(
                OrganizationChartConfigurationError,
                "ORG_CHART_FONT_PATH",
            ):
                chart_module._resolve_font_path()


class OrganizationChartRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generate_endpoint_returns_structure_and_jpeg(self):
        with (
            patch(
                "app.domains.planning_resources.router.planning_resource_graph",
                FakeGraph(),
            ),
            patch.object(chart_module, "_load_fonts", default_fonts),
        ):
            response = self.client.post(
                "/api/v1/planning/resources/organization-chart/generate",
                json={
                    "planning_request": planning_payload(),
                    "organization_metadata": metadata_payload(),
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["organization"]["project_manager"], 1)
        self.assertEqual(len(body["organization"]["teams"]), 8)
        self.assertTrue(
            base64.b64decode(body["image_base64"]).startswith(b"\xff\xd8\xff")
        )

    def test_manual_render_endpoint_does_not_invoke_allocation_ai(self):
        request, view = build_view()
        render_request = OrganizationChartRenderRequest(
            planning_request=request,
            organization=move_member(view, 8, 3),
        )
        with (
            patch(
                "app.domains.planning_resources.router.planning_resource_graph",
                FailingGraph(),
            ),
            patch.object(chart_module, "_load_fonts", default_fonts),
        ):
            response = self.client.post(
                "/api/v1/planning/resources/organization-chart/render",
                json=render_request.model_dump(mode="json"),
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["organization"], render_request.model_dump(mode="json")["organization"])
        self.assertTrue(
            base64.b64decode(body["image_base64"]).startswith(b"\xff\xd8\xff")
        )


if __name__ == "__main__":
    unittest.main()
