from __future__ import annotations

import importlib
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.domains.planning_costs.graph import PlanningCostGraph
from app.domains.planning_costs.llm_service import GeneratedCostAnalysis
from app.domains.planning_documents.graph import PlanningDocumentGraph
from app.domains.planning_resources.graph import PlanningResourceGraph
from app.domains.planning_resources.llm_service import (
    GeneratedResourcePlan,
    GeneratedTaskResourceEstimate,
)
from app.domains.planning_schedule.graph import PlanningScheduleGraph
from app.domains.planning_schedule.llm_service import (
    GeneratedSchedulePlan,
    GeneratedTaskScheduleEstimate,
)
from app.domains.planning_schedule.service import PlanningScheduleService
from app.domains.planning_wbs.graph import PlanningWBSGraph
from app.domains.planning_wbs.llm_service import (
    GeneratedWBSPhase,
    GeneratedWBSPlan,
    GeneratedWBSTask,
    GeneratedWBSWorkPackage,
)
from app.main import app


class FakeDocumentLlm:
    def extract(self, chunks, vision_documents, fallback_extractions):
        source_document = chunks[0]["source_document"]
        return [
            {
                "project_info": {
                    "project_name": "AIPM integration",
                    "project_goal": "Validate the planning pipeline",
                    "client_organization": "AIVLE",
                    "period_start": "2026-08-03",
                    "period_end": "2026-09-30",
                    "key_features": ["planning"],
                    "required_artifacts": [
                        {
                            "artifact_type": "REQUIREMENTS_DEFINITION",
                            "artifact_name": "Requirements",
                            "required_version": "1.0",
                        }
                    ],
                    "acceptance_conditions": ["Pipeline tests pass"],
                    "budget_contract_conditions": [],
                    "security_privacy_conditions": [],
                },
                "requirements": [
                    {
                        "function_name": "Planning API",
                        "requirement_text": (
                            "The system must generate a project plan."
                        ),
                        "category": "FUNCTIONAL",
                        "priority": "HIGH",
                        "acceptance_criteria": "A plan is returned",
                        "due_date": None,
                        "deliverable_name": "Requirements",
                        "security_condition": None,
                        "source_document": source_document,
                        "source_excerpt": "generate a project plan",
                    },
                    {
                        "function_name": "Authorization",
                        "requirement_text": (
                            "The system must authorize planning requests."
                        ),
                        "category": "SECURITY",
                        "priority": "HIGH",
                        "acceptance_criteria": "Unauthorized access is denied",
                        "due_date": None,
                        "deliverable_name": None,
                        "security_condition": "Bearer authentication",
                        "source_document": source_document,
                        "source_excerpt": "authorize planning requests",
                    },
                ],
            }
        ], "SUCCEEDED"


class FakeWbsLlm:
    def generate(self, contexts):
        requirement_ids = sorted(
            {
                item["requirement_id"]
                for context in contexts
                for item in context["requirements"]
            }
        )
        artifact_types = sorted(
            {
                artifact["artifact_type"]
                for context in contexts
                for artifact in context["project"]["required_artifacts"]
            }
        )
        methodology = contexts[0]["methodology"]
        return [
            GeneratedWBSPlan(
                phases=[
                    GeneratedWBSPhase(
                        phase_name=methodology[0],
                        description="Plan the project",
                        completion_criteria=["Planning is complete"],
                        work_packages=[
                            GeneratedWBSWorkPackage(
                                name="Planning package",
                                description="Prepare the delivery plan",
                                completion_criteria=["Plan is reviewed"],
                                tasks=[
                                    GeneratedWBSTask(
                                        name="Create plan",
                                        description=(
                                            "Create the authorized project plan"
                                        ),
                                        mapped_requirement_ids=requirement_ids,
                                        related_artifact_types=artifact_types,
                                        completion_criteria=[
                                            "All requirements are mapped"
                                        ],
                                    )
                                ],
                            )
                        ],
                    )
                ]
            )
        ]


class FakeScheduleLlm:
    def generate(self, context):
        estimates = []
        previous_id = None
        for task in context["tasks"]:
            estimates.append(
                GeneratedTaskScheduleEstimate(
                    wbs_id=task["wbs_id"],
                    optimistic_days=1,
                    most_likely_days=2,
                    pessimistic_days=3,
                    predecessor_wbs_ids=(
                        [] if previous_id is None else [previous_id]
                    ),
                )
            )
            previous_id = task["wbs_id"]
        return GeneratedSchedulePlan(task_estimates=estimates)


class FakeResourceLlm:
    def generate(self, contexts):
        return [
            GeneratedResourcePlan(
                task_estimates=[
                    GeneratedTaskResourceEstimate(
                        wbs_id=task["wbs_id"],
                        required_role_code="BACKEND_DEVELOPER",
                        required_skills=[],
                        estimated_person_days=1.0,
                        estimation_reason="Small integration task",
                    )
                    for task in context["tasks"]
                ]
            )
            for context in contexts
        ]


class FakeCostLlm:
    def generate(self, context):
        return GeneratedCostAnalysis(potential_additional_costs=[])


class PlanningApiPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_document_to_wbs_schedule_resource_and_cost_pipeline(self):
        document_graph = PlanningDocumentGraph(llm_service=FakeDocumentLlm())
        wbs_graph = PlanningWBSGraph(llm_service=FakeWbsLlm())
        schedule_graph = PlanningScheduleGraph(
            schedule_service=PlanningScheduleService(
                monte_carlo_iterations=100,
                random_seed=17,
            ),
            llm_service=FakeScheduleLlm(),
        )
        resource_graph = PlanningResourceGraph(
            llm_service=FakeResourceLlm()
        )
        cost_graph = PlanningCostGraph(llm_service=FakeCostLlm())

        patches = (
            (
                "app.domains.planning_documents.router",
                "planning_document_graph",
                document_graph,
            ),
            (
                "app.domains.planning_wbs.router",
                "planning_wbs_graph",
                wbs_graph,
            ),
            (
                "app.domains.planning_schedule.router",
                "planning_schedule_graph",
                schedule_graph,
            ),
            (
                "app.domains.planning_resources.router",
                "planning_resource_graph",
                resource_graph,
            ),
            (
                "app.domains.planning_costs.router",
                "planning_cost_graph",
                cost_graph,
            ),
        )

        with ExitStack() as stack:
            for module_name, attribute, value in patches:
                module = importlib.import_module(module_name)
                stack.enter_context(patch.object(module, attribute, value))

            document_response = self.client.post(
                "/api/v1/planning/documents/extract",
                files=[
                    (
                        "files",
                        (
                            "rfp.txt",
                            b"Project planning requirements",
                            "text/plain",
                        ),
                    )
                ],
            )
            self.assertEqual(document_response.status_code, 200)
            document = document_response.json()
            self.assertEqual(document["llm_status"], "SUCCEEDED")
            self.assertEqual(len(document["requirement_candidates"]), 2)

            wbs_response = self.client.post(
                "/api/v1/planning/wbs/generate",
                json={
                    "project_info": document["project_info"],
                    "requirement_candidates": document[
                        "requirement_candidates"
                    ],
                    "methodology": ["Planning"],
                },
            )
            self.assertEqual(wbs_response.status_code, 200)
            wbs = wbs_response.json()
            self.assertEqual(wbs["generation_status"], "SUCCEEDED")
            self.assertEqual(
                wbs["requirement_coverage"]["coverage_rate"],
                100.0,
            )

            schedule_items = [
                {
                    key: item[key]
                    for key in (
                        "wbs_id",
                        "wbs_code",
                        "parent_wbs_id",
                        "item_type",
                        "wbs_name",
                        "description",
                    )
                }
                for item in wbs["wbs_items"]
            ]
            schedule_response = self.client.post(
                "/api/v1/planning/schedules/recommend",
                json={
                    "project_id": 7,
                    "project_start_date": "2026-08-03",
                    "target_end_date": "2026-09-30",
                    "wbs_items": schedule_items,
                },
            )
            self.assertEqual(schedule_response.status_code, 200)
            schedule = schedule_response.json()
            self.assertEqual(
                len(schedule["wbs_schedules"]),
                len(wbs["wbs_items"]),
            )

            recommended_dates = {
                item["wbs_id"]: item["recommended"]
                for item in schedule["wbs_schedules"]
            }
            task_items = [
                item
                for item in wbs["wbs_items"]
                if item["item_type"] == "TASK"
            ]
            resource_response = self.client.post(
                "/api/v1/planning/resources/recommend",
                json={
                    "project_id": 7,
                    "wbs_tasks": [
                        {
                            "wbs_id": item["wbs_id"],
                            "wbs_name": item["wbs_name"],
                            "description": item["description"],
                            "start_date": recommended_dates[
                                item["wbs_id"]
                            ]["start_date"],
                            "end_date": recommended_dates[item["wbs_id"]][
                                "end_date"
                            ],
                        }
                        for item in task_items
                    ],
                    "project_members": [
                        {
                            "project_member_id": 101,
                            "roles": ["BACKEND_DEVELOPER"],
                            "skills": [],
                            "allocations": [
                                {
                                    "allocation_start_date": "2026-08-03",
                                    "allocation_end_date": "2026-09-30",
                                    "available_hours_per_week": 40,
                                    "allocation_status": "ACTIVE",
                                }
                            ],
                        }
                    ],
                },
            )
            self.assertEqual(resource_response.status_code, 200)
            resources = resource_response.json()
            self.assertEqual(len(resources["assignments"]), len(task_items))
            self.assertEqual(resources["unassigned_wbs_ids"], [])

            task_by_id = {
                item["wbs_id"]: item
                for item in task_items
            }
            cost_response = self.client.post(
                "/api/v1/planning/costs/estimate",
                json={
                    "project_id": 7,
                    "project_name": document["project_info"][
                        "project_name"
                    ],
                    "wbs_efforts": [
                        {
                            "wbs_id": assignment["wbs_id"],
                            "wbs_name": task_by_id[
                                assignment["wbs_id"]
                            ]["wbs_name"],
                            "description": task_by_id[
                                assignment["wbs_id"]
                            ]["description"],
                            "estimated_mm": assignment["estimated_mm"],
                        }
                        for assignment in resources["assignments"]
                    ],
                    "average_monthly_unit_price": 8_000_000,
                    "operation_months": 6,
                    "service_scale": "SMALL",
                    "uses_ai_api": False,
                    "paid_license_user_count": 0,
                    "include_vat": True,
                },
            )
            self.assertEqual(cost_response.status_code, 200)
            cost = cost_response.json()
            self.assertEqual(cost["project_id"], 7)
            self.assertEqual(
                cost["total_estimated_mm"],
                resources["total_estimated_mm"],
            )
            self.assertGreater(cost["estimate"]["total_amount"], 0)


if __name__ == "__main__":
    unittest.main()
