from __future__ import annotations

from copy import deepcopy


def project_info_payload() -> dict:
    return {
        "project_name": "AIPM Delivery Platform",
        "project_goal": "Automate project planning",
        "client_organization": "AIVLE",
        "period_start": "2026-08-03",
        "period_end": "2026-12-31",
        "key_features": ["planning", "risk"],
        "required_artifacts": [
            {
                "artifact_type": "REQUIREMENTS_DEFINITION",
                "artifact_name": "Requirements",
                "required_version": "1.0",
            },
            {
                "artifact_type": "TEST_RESULTS",
                "artifact_name": "Test results",
                "required_version": "1.0",
            },
        ],
        "acceptance_conditions": ["Tests pass"],
        "budget_contract_conditions": [],
        "security_privacy_conditions": ["Secrets are masked"],
    }


def requirement_payloads(count: int = 2) -> list[dict]:
    result = []
    for index in range(1, count + 1):
        result.append(
            {
                "requirement_id": index,
                "function_name": f"Feature {index}",
                "requirement_text": f"The system must implement feature {index}.",
                "category": "FUNCTIONAL" if index == 1 else "SECURITY",
                "priority": "HIGH",
                "acceptance_criteria": f"Feature {index} is verified",
                "due_date": None,
                "deliverable_name": None,
                "security_condition": (
                    None if index == 1 else "Access must be authorized"
                ),
                "source_document": "rfp.txt",
                "source_excerpt": f"Feature {index}",
            }
        )
    return result


def wbs_request_payload(requirement_count: int = 2) -> dict:
    return {
        "project_info": project_info_payload(),
        "requirement_candidates": requirement_payloads(requirement_count),
        "methodology": ["Analysis", "Build"],
    }


def wbs_items_payload() -> list[dict]:
    return [
        {
            "wbs_id": 1,
            "wbs_code": "1",
            "parent_wbs_id": None,
            "item_type": "PHASE",
            "wbs_name": "Analysis",
            "description": "Analyze requirements",
        },
        {
            "wbs_id": 2,
            "wbs_code": "1.1",
            "parent_wbs_id": 1,
            "item_type": "WORK_PACKAGE",
            "wbs_name": "Requirements",
            "description": "Prepare requirements",
        },
        {
            "wbs_id": 3,
            "wbs_code": "1.1.1",
            "parent_wbs_id": 2,
            "item_type": "TASK",
            "wbs_name": "Review requirements",
            "description": "Review requirements with stakeholders",
        },
        {
            "wbs_id": 4,
            "wbs_code": "2",
            "parent_wbs_id": None,
            "item_type": "PHASE",
            "wbs_name": "Build",
            "description": "Build the service",
        },
        {
            "wbs_id": 5,
            "wbs_code": "2.1",
            "parent_wbs_id": 4,
            "item_type": "WORK_PACKAGE",
            "wbs_name": "Backend",
            "description": "Build backend",
        },
        {
            "wbs_id": 6,
            "wbs_code": "2.1.1",
            "parent_wbs_id": 5,
            "item_type": "TASK",
            "wbs_name": "Implement API",
            "description": "Implement Spring API",
        },
    ]


def schedule_request_payload() -> dict:
    return {
        "project_id": 7,
        "project_start_date": "2026-08-03",
        "target_end_date": "2026-09-30",
        "wbs_items": deepcopy(wbs_items_payload()),
    }


def resource_request_payload() -> dict:
    return {
        "project_id": 7,
        "wbs_tasks": [
            {
                "wbs_id": 3,
                "wbs_name": "Review requirements",
                "description": "Review requirements with stakeholders",
                "start_date": "2026-08-03",
                "end_date": "2026-08-07",
            },
            {
                "wbs_id": 6,
                "wbs_name": "Implement API",
                "description": "Implement Spring API",
                "start_date": "2026-08-10",
                "end_date": "2026-08-14",
            },
        ],
        "project_members": [
            {
                "project_member_id": 10,
                "roles": ["REQUIREMENT_ANALYST", "BACKEND_DEVELOPER"],
                "skills": [
                    {
                        "skill_code": "REQUIREMENT_ANALYSIS",
                        "proficiency_level": 5,
                        "experience_months": 60,
                    },
                    {
                        "skill_code": "SPRING_BOOT",
                        "proficiency_level": 4,
                        "experience_months": 36,
                    },
                ],
                "allocations": [
                    {
                        "allocation_start_date": "2026-08-03",
                        "allocation_end_date": "2026-08-31",
                        "available_hours_per_week": 40,
                        "allocation_status": "ACTIVE",
                    }
                ],
            },
            {
                "project_member_id": 11,
                "roles": ["BACKEND_DEVELOPER"],
                "skills": [
                    {
                        "skill_code": "SPRING_BOOT",
                        "proficiency_level": 3,
                        "experience_months": 12,
                    }
                ],
                "allocations": [
                    {
                        "allocation_start_date": "2026-08-03",
                        "allocation_end_date": None,
                        "available_hours_per_week": 20,
                        "allocation_status": "PLANNED",
                    }
                ],
            },
        ],
    }


def cost_request_payload() -> dict:
    return {
        "project_id": 7,
        "project_name": "AIPM Delivery Platform",
        "wbs_efforts": [
            {
                "wbs_id": 3,
                "wbs_name": "Review requirements",
                "description": "Review requirements with stakeholders",
                "estimated_mm": 0.5,
            },
            {
                "wbs_id": 6,
                "wbs_name": "Implement API",
                "description": "Implement Spring API",
                "estimated_mm": 1.25,
            },
        ],
        "average_monthly_unit_price": 8_000_000,
        "operation_months": 6,
        "service_scale": "SMALL",
        "uses_ai_api": True,
        "paid_license_user_count": 3,
        "include_vat": True,
    }
