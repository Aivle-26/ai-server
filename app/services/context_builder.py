from sqlalchemy.orm import Session

from app.models.normalized_event import NormalizedEvent
from app.models.project import Project


class ContextBuilder:

    def _get_project(
        self,
        db: Session,
        project_id: int,
    ) -> Project:
        project = (
            db.query(Project)
            .filter(Project.project_id == project_id)
            .first()
        )

        if project is None:
            raise ValueError(
                f"project_id={project_id}인 프로젝트를 찾을 수 없습니다."
            )

        return project

    def _serialize_project(
        self,
        project: Project,
    ) -> dict:
        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "project_code": project.project_code,
            "description": project.description,
            "project_goal": project.project_goal,
            "start_date": (
                project.start_date.isoformat()
                if project.start_date
                else None
            ),
            "end_date": (
                project.end_date.isoformat()
                if project.end_date
                else None
            ),
            "status": project.status,
        }

    def _serialize_event(
        self,
        event: NormalizedEvent,
    ) -> dict:
        return {
            "normalized_event_id":
                event.normalized_event_id,
            "source_type": event.source_type,
            "event_type": event.event_type,
            "title": event.title,
            "content": event.content,
            "status": event.status,
            "priority": event.priority,
            "actor_external_id":
                event.actor_external_id,
            "occurred_at": (
                event.occurred_at.isoformat()
                if event.occurred_at
                else None
            ),
            "metadata": event.metadata_json,
        }

    def build_common_context(
        self,
        db: Session,
        project_id: int,
    ) -> dict:
        project = self._get_project(
            db=db,
            project_id=project_id,
        )

        events = (
            db.query(NormalizedEvent)
            .filter(
                NormalizedEvent.project_id == project_id
            )
            .order_by(
                NormalizedEvent.occurred_at.desc()
            )
            .all()
        )

        event_data = [
            self._serialize_event(event)
            for event in events
        ]

        return {
            "project": self._serialize_project(project),
            "events": event_data,
            "event_count": len(event_data),
        }

    def build_planning_context(
        self,
        db: Session,
        project_id: int,
    ) -> dict:
        common_context = self.build_common_context(
            db=db,
            project_id=project_id,
        )

        planning_events = [
            event
            for event in common_context["events"]
            if event["source_type"] in {
                "GITHUB",
                "JIRA",
            }
            and event["event_type"] in {
                "ISSUE",
                "TASK",
                "STORY",
                "EPIC",
                "BUG",
            }
        ]

        return {
            "context_type": "PLANNING",
            "project": common_context["project"],
            "planning_events": planning_events,
            "planning_event_count":
                len(planning_events),
        }

    def build_report_context(
        self,
        db: Session,
        project_id: int,
    ) -> dict:
        common_context = self.build_common_context(
            db=db,
            project_id=project_id,
        )

        report_events = [
            event
            for event in common_context["events"]
            if event["event_type"] in {
                "COMMIT",
                "PULL_REQUEST",
                "TASK",
                "STORY",
                "ISSUE",
            }
        ]

        completed_events = [
            event
            for event in report_events
            if event["status"] in {
                "DONE",
                "COMPLETED",
                "CLOSED",
                "MERGED",
                "RESOLVED",
            }
        ]

        in_progress_events = [
            event
            for event in report_events
            if event["status"] in {
                "OPEN",
                "IN PROGRESS",
                "IN_PROGRESS",
                "REVIEW",
            }
        ]

        return {
            "context_type": "REPORT",
            "project": common_context["project"],
            "report_events": report_events,
            "completed_events": completed_events,
            "in_progress_events": in_progress_events,
            "report_event_count": len(report_events),
        }

    def build_risk_context(
        self,
        db: Session,
        project_id: int,
    ) -> dict:
        common_context = self.build_common_context(
            db=db,
            project_id=project_id,
        )

        risk_events = [
            event
            for event in common_context["events"]
            if event["priority"] in {
                "HIGH",
                "CRITICAL",
            }
            or event["source_type"] == "SLACK"
            or event["status"] in {
                "BLOCKED",
                "FAILED",
                "OVERDUE",
            }
        ]

        critical_events = [
            event
            for event in risk_events
            if event["priority"] == "CRITICAL"
        ]

        high_events = [
            event
            for event in risk_events
            if event["priority"] == "HIGH"
        ]

        return {
            "context_type": "RISK",
            "project": common_context["project"],
            "risk_events": risk_events,
            "critical_events": critical_events,
            "high_events": high_events,
            "risk_event_count": len(risk_events),
        }