from typing import Any


class ReportAgent:

    def generate(
        self,
        report_context: dict[str, Any],
    ) -> dict[str, Any]:

        project = report_context["project"]
        events = report_context["report_events"]

        completed = report_context["completed_events"]
        in_progress = report_context["in_progress_events"]

        summary = {
            "project_name": project["project_name"],
            "project_status": project["status"],
            "total_events": len(events),
            "completed_count": len(completed),
            "in_progress_count": len(in_progress),
            "completion_rate": self._completion_rate(
                completed,
                events,
            ),
            "summary_text": self._make_summary(
                project,
                completed,
                in_progress,
            ),
        }

        return summary

    def _completion_rate(
        self,
        completed,
        total,
    ):

        if len(total) == 0:
            return 0

        return round(
            len(completed) / len(total) * 100,
            2,
        )

    def _make_summary(
        self,
        project,
        completed,
        in_progress,
    ):

        return (
            f"{project['project_name']} 프로젝트는 "
            f"{project['status']} 상태이며 "
            f"완료 {len(completed)}건, "
            f"진행중 {len(in_progress)}건입니다."
        )
