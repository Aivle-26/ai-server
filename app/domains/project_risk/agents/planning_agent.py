from typing import Any


class PlanningAgent:
    def analyze(
        self,
        planning_context: dict[str, Any],
    ) -> dict[str, Any]:

        events = planning_context.get(
            "planning_events",
            []
        )

        requirements = []
        wbs_tasks = []

        for index, event in enumerate(events, start=1):
            requirement_code = f"REQ-{index:03d}"

            requirement = {
                "requirement_code": requirement_code,
                "title": event.get("title"),
                "description": event.get("content"),
                "requirement_type": self._classify_type(
                    event=event
                ),
                "priority": event.get("priority") or "MEDIUM",
                "status": "DRAFT",
                "source_type": event.get("source_type"),
                "source_event_id": event.get(
                    "normalized_event_id"
                ),
                "acceptance_criteria":
                    self._make_acceptance_criteria(
                        event=event
                    ),
            }

            requirements.append(requirement)

            generated_tasks = self._make_wbs_tasks(
                event=event,
                requirement_code=requirement_code,
            )

            wbs_tasks.extend(generated_tasks)

        return {
            "agent_type": "PLANNING",
            "output_type": "REQUIREMENTS_AND_WBS",
            "project_id": planning_context[
                "project"
            ]["project_id"],
            "requirement_count": len(requirements),
            "wbs_count": len(wbs_tasks),
            "requirements": requirements,
            "wbs_tasks": wbs_tasks,
        }

    def _classify_type(
        self,
        event: dict[str, Any],
    ) -> str:

        title = str(event.get("title") or "")
        content = str(event.get("content") or "")

        combined_text = f"{title} {content}".lower()

        non_functional_keywords = [
            "응답 시간",
            "처리 속도",
            "동시 접속",
            "가용성",
            "개인정보 보호",
            "접근 권한",
            "감사 로그",
            "시스템 로그",
            "암호화",
            "보안 정책",
            "성능 기준",
            "복구 시간",
        ]

        if any(
            keyword in combined_text
            for keyword in non_functional_keywords
        ):
            return "NON_FUNCTIONAL"

        return "FUNCTIONAL"

    def _make_acceptance_criteria(
        self,
        event: dict[str, Any],
    ) -> str:

        title = event.get("title") or "해당 기능"

        return (
            f"{title} 관련 기능이 정상적으로 동작하고, "
            "오류 없이 테스트를 통과해야 한다."
        )

    def _make_wbs_tasks(
        self,
        event: dict[str, Any],
        requirement_code: str,
    ) -> list[dict[str, Any]]:

        title = event.get("title") or "기능 개발"

        task_templates = [
            {
                "task_name": f"{title} 원인 및 요구사항 분석",
                "task_description": (
                    f"{title} 관련 현상과 요구사항을 분석한다."
                ),
                "estimated_days": 1,
            },
            {
                "task_name": f"{title} 설계",
                "task_description": (
                    f"{title} 구현을 위한 처리 흐름과 구조를 설계한다."
                ),
                "estimated_days": 1,
            },
            {
                "task_name": f"{title} 구현",
                "task_description": (
                    f"{title} 관련 기능을 개발한다."
                ),
                "estimated_days": 2,
            },
            {
                "task_name": f"{title} 테스트",
                "task_description": (
                    f"{title} 기능의 정상 동작과 예외 상황을 검증한다."
                ),
                "estimated_days": 1,
            },
        ]

        result = []

        for order, task in enumerate(
            task_templates,
            start=1,
        ):
            result.append(
                {
                    "requirement_code": requirement_code,
                    "task_name": task["task_name"],
                    "task_description":
                        task["task_description"],
                    "task_order": order,
                    "estimated_days":
                        task["estimated_days"],
                    "status": "TODO",
                }
            )

        return result