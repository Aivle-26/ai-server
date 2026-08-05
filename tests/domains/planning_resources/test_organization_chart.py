from __future__ import annotations

import base64
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image, ImageFont

from app.domains.planning_resources import organization_chart as chart_module
from app.domains.planning_resources.organization_chart import (
    OrganizationChartConfigurationError,
    OrganizationChartGenerationRequest,
    render_organization_chart,
)
from app.domains.planning_resources.schemas import PlanningResourceRequest
from app.domains.planning_resources.view_builders import build_organization_chart
from app.main import app


def planning_payload() -> dict:
    return {
        "project_id": 7,
        "project_name": "AIVLE 통합 프로젝트",
        "wbs_tasks": [
            {
                "wbs_id": 3,
                "wbs_name": "백엔드 API 구현",
                "description": "조직도 API를 구현합니다.",
                "start_date": "2026-08-03",
                "end_date": "2026-08-07",
            },
            {
                "wbs_id": 6,
                "wbs_name": "프론트 미리보기 구현",
                "description": "보호된 JPG 미리보기를 구현합니다.",
                "start_date": "2026-08-10",
                "end_date": "2026-08-14",
            },
        ],
        "project_members": [
            {
                "project_member_id": 10,
                "member_name": "김 프로젝트매니저",
                "roles": ["PM"],
                "skills": [],
                "allocations": [],
            },
            {
                "project_member_id": 11,
                "member_name": "박 백엔드개발자 매우긴이름 테스트",
                "roles": ["BACKEND", "TECH_LEAD"],
                "skills": [],
                "allocations": [],
            },
            {
                "project_member_id": 12,
                "member_name": "이 프론트엔드개발자",
                "roles": ["FRONTEND"],
                "skills": [],
                "allocations": [],
            },
        ],
    }


def recommendation_payload() -> dict:
    return {
        "project_id": 7,
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
                "required_skills": [],
                "estimated_person_days": 2,
                "estimated_hours": 16,
                "estimated_mm": 0.1,
                "required_headcount": 1,
                "recommended_members": [
                    {
                        "project_member_id": 11,
                        "recommendation_score": 95,
                        "assigned_hours": 16,
                        "remaining_available_hours": 16,
                    }
                ],
                "recommendation_reason": "Qualified backend member",
            },
            {
                "wbs_id": 6,
                "required_role_code": "FRONTEND",
                "required_skills": [],
                "estimated_person_days": 2,
                "estimated_hours": 16,
                "estimated_mm": 0.1,
                "required_headcount": 2,
                "recommended_members": [
                    {
                        "project_member_id": 12,
                        "recommendation_score": 90,
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
        "unassigned_wbs_ids": [6],
        "warnings": ["Frontend capacity is short"],
        "llm_status": "SUCCEEDED",
    }


def metadata_payload() -> dict:
    return {
        "project_manager_member_id": 10,
        "teams": [
            {
                "role_code": "BACKEND",
                "team_name": "플랫폼 백엔드 팀",
                "leader_member_id": 11,
                "collaborates_with_role_codes": ["FRONTEND"],
            },
            {
                "role_code": "FRONTEND",
                "team_name": "사용자 경험 프론트엔드 팀",
                "leader_member_id": 12,
                "reports_to_role_code": "BACKEND",
            },
        ],
    }


def default_fonts() -> chart_module._Fonts:
    font = ImageFont.load_default()
    return chart_module._Fonts(font, font, font, font)


class FakeGraph:
    def invoke(self, request):
        return recommendation_payload()


class OrganizationChartTest(unittest.TestCase):
    def setUp(self):
        self.request = PlanningResourceRequest.model_validate(planning_payload())

    def build_view(self, metadata: dict | None = None):
        from datetime import datetime, timezone

        return build_organization_chart(
            self.request,
            recommendation_payload(),
            metadata=metadata,
            generated_at=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
        )

    def test_request_accepts_existing_contract_and_optional_metadata(self):
        parsed = OrganizationChartGenerationRequest.model_validate(
            {
                "planning_request": planning_payload(),
                "organization_metadata": metadata_payload(),
            }
        )

        self.assertEqual(parsed.planning_request.project_id, 7)
        self.assertEqual(parsed.organization_metadata.project_manager_member_id, 10)

    def test_render_contains_multiple_teams_members_gaps_and_unassigned_wbs(self):
        view = self.build_view(metadata_payload())

        with patch.object(chart_module, "_load_fonts", default_fonts):
            rendered = render_organization_chart(self.request, view)

        self.assertTrue(rendered.content.startswith(b"\xff\xd8\xff"))
        self.assertGreater(rendered.width, 0)
        self.assertGreater(rendered.height, 0)
        self.assertEqual(view.project_manager, 10)
        self.assertEqual(len(view.teams), 2)
        self.assertEqual(view.teams[0].multi_role_members, [11])
        self.assertEqual(view.role_gaps[0].role_code, "FRONTEND")
        self.assertEqual(view.unassigned_wbs_ids, [6])
        with Image.open(BytesIO(rendered.content)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (rendered.width, rendered.height))

    def test_render_supports_missing_pm_and_long_names_without_overflow(self):
        payload = planning_payload()
        for index in range(13, 40):
            payload["project_members"].append(
                {
                    "project_member_id": index,
                    "member_name": "매우 긴 조직도 팀원 이름 " * 4 + str(index),
                    "roles": ["BACKEND"],
                    "skills": [],
                    "allocations": [],
                }
            )
        request = PlanningResourceRequest.model_validate(payload)
        response = recommendation_payload()
        response["assignments"][0]["recommended_members"].extend(
            {
                "project_member_id": index,
                "recommendation_score": 80,
                "assigned_hours": 1,
                "remaining_available_hours": 1,
            }
            for index in range(13, 40)
        )
        from datetime import datetime, timezone

        view = build_organization_chart(
            request,
            response,
            generated_at=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc),
        )

        with patch.object(chart_module, "_load_fonts", default_fonts):
            rendered = render_organization_chart(request, view)

        self.assertIsNone(view.project_manager)
        self.assertLessEqual(rendered.width, chart_module.MAX_IMAGE_WIDTH)
        self.assertLessEqual(rendered.height, chart_module.MAX_IMAGE_HEIGHT)

    def test_builder_rejects_invalid_pm_leader_relationship_and_cycle(self):
        invalid = [
            {"project_manager_member_id": 999},
            {"teams": [{"role_code": "BACKEND", "leader_member_id": 12}]},
            {"teams": [{"role_code": "BACKEND", "reports_to_role_code": "QA"}]},
            {
                "teams": [
                    {"role_code": "BACKEND", "reports_to_role_code": "FRONTEND"},
                    {"role_code": "FRONTEND", "reports_to_role_code": "BACKEND"},
                ]
            },
        ]
        for metadata in invalid:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                self.build_view(metadata)

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

    def test_endpoint_returns_valid_json_and_jpeg(self):
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
        self.assertEqual(body["content_type"], "image/jpeg")
        self.assertEqual(body["file_name"], "project-7-organization-chart.jpg")
        self.assertTrue(base64.b64decode(body["image_base64"]).startswith(b"\xff\xd8\xff"))
        self.assertGreater(body["width"], 0)
        self.assertGreater(body["height"], 0)
        self.assertEqual(body["organization"]["project_id"], 7)

    def test_endpoint_maps_font_failure_to_503(self):
        with (
            patch(
                "app.domains.planning_resources.router.planning_resource_graph",
                FakeGraph(),
            ),
            patch.object(
                chart_module,
                "_load_fonts",
                side_effect=OrganizationChartConfigurationError("font missing"),
            ),
        ):
            response = self.client.post(
                "/api/v1/planning/resources/organization-chart/generate",
                json={"planning_request": planning_payload()},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["message"], "font missing")


if __name__ == "__main__":
    unittest.main()
