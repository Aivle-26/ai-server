from typing import Any


class RiskAgent:

    def analyze(
        self,
        risk_context: dict[str, Any],
    ) -> dict[str, Any]:

        risk_events = risk_context.get(
            "risk_events",
            []
        )

        risks = []

        for index, event in enumerate(
            risk_events,
            start=1,
        ):
            risk = {
                "risk_code": f"RISK-{index:03d}",
                "risk_type": self._classify_risk_type(
                    event=event
                ),
                "risk_title": event.get("title"),
                "risk_description": event.get("content"),
                "probability_score":
                    self._calculate_probability(
                        event=event
                    ),
                "impact_score":
                    self._calculate_impact(
                        event=event
                    ),
                "risk_level": self._calculate_level(
                    event=event
                ),
                "status": "OPEN",
                "detection_source":
                    event.get("source_type"),
                "source_event_id":
                    event.get("normalized_event_id"),
                "evidence_text":
                    event.get("content"),
                "recommended_actions":
                    self._make_recommendations(
                        event=event
                    ),
            }

            risks.append(risk)

        return {
            "agent_type": "RISK",
            "output_type": "RISKS",
            "project_id": risk_context[
                "project"
            ]["project_id"],
            "risk_count": len(risks),
            "risks": risks,
        }

    def _classify_risk_type(
        self,
        event: dict[str, Any],
    ) -> str:

        text = (
            f"{event.get('title', '')} "
            f"{event.get('content', '')}"
        ).lower()

        if event.get("source_type") == "SLACK":
            return "COMMUNICATION"

        if any(
            keyword in text
            for keyword in [
                "지연",
                "마감",
                "due",
                "overdue",
            ]
        ):
            return "SCHEDULE"

        if any(
            keyword in text
            for keyword in [
                "보안",
                "개인정보",
                "토큰",
                "인증",
                "권한",
            ]
        ):
            return "SECURITY"

        if any(
            keyword in text
            for keyword in [
                "오류",
                "에러",
                "실패",
                "bug",
            ]
        ):
            return "QUALITY"

        return "PROJECT"

    def _calculate_probability(
        self,
        event: dict[str, Any],
    ) -> float:

        priority = event.get("priority")

        if priority == "CRITICAL":
            return 0.9

        if priority == "HIGH":
            return 0.7

        if priority == "MEDIUM":
            return 0.5

        return 0.3

    def _calculate_impact(
        self,
        event: dict[str, Any],
    ) -> float:

        if event.get("source_type") == "SLACK":
            return 0.8

        if event.get("status") in {
            "BLOCKED",
            "FAILED",
            "OVERDUE",
        }:
            return 0.9

        if event.get("priority") == "CRITICAL":
            return 0.9

        if event.get("priority") == "HIGH":
            return 0.7

        return 0.5

    def _calculate_level(
        self,
        event: dict[str, Any],
    ) -> str:

        score = (
            self._calculate_probability(event)
            * self._calculate_impact(event)
        )

        if score >= 0.75:
            return "CRITICAL"

        if score >= 0.5:
            return "HIGH"

        if score >= 0.25:
            return "MEDIUM"

        return "LOW"

    def _make_recommendations(
        self,
        event: dict[str, Any],
    ) -> list[str]:

        risk_type = self._classify_risk_type(
            event=event
        )

        recommendation_map = {
            "COMMUNICATION": [
                "담당자와 현재 진행 상태를 확인한다.",
                "미응답 업무와 결정 대기 항목을 정리한다.",
            ],
            "SCHEDULE": [
                "관련 WBS 일정과 마감일을 재검토한다.",
                "필요하면 담당자 또는 작업 시간을 재배정한다.",
            ],
            "SECURITY": [
                "인증 및 권한 처리 로직을 점검한다.",
                "보안 테스트와 로그 검토를 진행한다.",
            ],
            "QUALITY": [
                "오류 재현 조건을 확인한다.",
                "수정 후 회귀 테스트를 수행한다.",
            ],
            "PROJECT": [
                "PM이 원인과 영향 범위를 검토한다.",
            ],
        }

        return recommendation_map[risk_type]