from typing import Any


class ProgressDelayService:
    def analyze(
        self,
        members: list[dict[str, Any]],
    ) -> dict[str, Any]:

        results = []

        for member in members:

            assigned = member["assigned_task_count"]
            completed = member["completed_task_count"]

            if assigned == 0:
                progress_rate = 100

            else:
                progress_rate = round(
                    completed / assigned * 100,
                    1,
                )

            delay_score = self._calculate_delay_score(
                progress_rate,
                member["overdue_task_count"],
            )

            delay_level = self._delay_level(
                delay_score,
            )

            results.append(
                {
                    "member_id": member["member_id"],
                    "member_name": member["member_name"],
                    "assigned_task_count": assigned,
                    "completed_task_count": completed,
                    "overdue_task_count":
                        member["overdue_task_count"],
                    "progress_rate":
                        progress_rate,
                    "delay_score":
                        delay_score,
                    "delay_level":
                        delay_level,
                    "recommended_action":
                        self._action(delay_level),
                }
            )

        return {
            "member_count": len(results),
            "delay_members": [
                member
                for member in results
                if member["delay_level"] != "LOW"
            ],
            "members": results,
        }

    def _calculate_delay_score(
        self,
        progress_rate: float,
        overdue_count: int,
    ) -> int:

        score = 0

        if progress_rate < 80:
            score += 20

        if progress_rate < 60:
            score += 20

        if progress_rate < 40:
            score += 20

        score += overdue_count * 10

        return min(score, 100)

    def _delay_level(
        self,
        score: int,
    ) -> str:

        if score >= 70:
            return "CRITICAL"

        if score >= 50:
            return "HIGH"

        if score >= 30:
            return "MEDIUM"

        return "LOW"

    def _action(
        self,
        level: str,
    ) -> str:

        actions = {
            "LOW":
                "현재 상태 유지",
            "MEDIUM":
                "진행 상황 확인",
            "HIGH":
                "업무 재배정 검토",
            "CRITICAL":
                "즉시 PM 개입",
        }

        return actions[level]