from datetime import date
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.project_risk.agents.assignment_agent import AssignmentAgent
from app.domains.project_risk.agents.planning_agent import PlanningAgent
from app.domains.project_risk.agents.report_agent import ReportAgent
from app.domains.project_risk.agents.risk_agent import RiskAgent
from app.domains.project_risk.models import (
    ExternalRawData,
    Member,
    MemberSkill,
    MemberWorkload,
    NormalizedEvent,
    Project,
    Requirement,
    Risk,
    Schedule,
    WBS,
)
from app.domains.project_risk.services.context_builder import ContextBuilder
from app.domains.project_risk.services.ingestion_service import IngestionService
from app.domains.project_risk.services.reassignment_service import (
    ReassignmentService,
)
from app.domains.project_risk.services.requirement_impact_service import (
    RequirementImpactService,
)
from app.domains.project_risk.services.requirement_service import (
    RequirementService,
)
from app.domains.project_risk.services.risk_service import RiskService
from app.domains.project_risk.services.schedule_service import ScheduleService
from app.domains.project_risk.services.wbs_service import WBSService


class ProjectRiskPersistenceServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.project = Project(
            project_name="AIPM",
            project_code="AIPM-TEST",
            description="Test project",
            project_goal="Verify project risk flow",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 12, 31),
            status="ACTIVE",
        )
        self.db.add(self.project)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def ingest_issue(self):
        return IngestionService().process(
            self.db,
            project_id=self.project.project_id,
            source_type="GITHUB",
            data_type="ISSUE",
            external_id="issue-1",
            payload={
                "number": 1,
                "title": "API login error",
                "body": "The API login fails and is overdue.",
                "state": "open",
                "labels": [{"name": "high"}],
                "user": {"login": "developer"},
                "created_at": "2026-07-20T10:00:00Z",
            },
        )

    def test_ingestion_persists_raw_and_normalized_event(self):
        result = self.ingest_issue()

        raw = self.db.get(ExternalRawData, result["raw_data_id"])
        event = self.db.get(
            NormalizedEvent, result["normalized_event_id"]
        )
        self.assertEqual(raw.processing_status, "NORMALIZED")
        self.assertEqual(event.source_type, "GITHUB")
        self.assertEqual(event.priority, "HIGH")
        self.assertEqual(event.title, "API login error")

    def test_ingestion_failure_marks_raw_data_failed(self):
        with self.assertRaises(ValueError):
            IngestionService().process(
                self.db,
                project_id=self.project.project_id,
                source_type="UNKNOWN",
                data_type="ITEM",
                external_id=None,
                payload={"value": 1},
            )

        raw = self.db.scalars(
            select(ExternalRawData).order_by(
                ExternalRawData.raw_data_id.desc()
            )
        ).first()
        self.assertEqual(raw.processing_status, "FAILED")
        self.assertIn("Adapter", raw.processing_error)

    def test_event_to_planning_assignment_schedule_risk_and_report_flow(self):
        self.ingest_issue()
        context_builder = ContextBuilder()
        planning_context = context_builder.build_planning_context(
            self.db, self.project.project_id
        )
        risk_context = context_builder.build_risk_context(
            self.db, self.project.project_id
        )
        report_context = context_builder.build_report_context(
            self.db, self.project.project_id
        )

        self.assertEqual(planning_context["planning_event_count"], 1)
        self.assertEqual(risk_context["risk_event_count"], 1)
        self.assertEqual(report_context["report_event_count"], 1)

        planning = PlanningAgent().analyze(planning_context)
        requirements = RequirementService().save_requirements(
            self.db,
            self.project.project_id,
            planning["requirements"],
        )
        tasks = WBSService().save_wbs_tasks(
            self.db,
            self.project.project_id,
            planning["wbs_tasks"],
        )
        self.assertEqual(len(requirements), 1)
        self.assertEqual(len(tasks), 4)

        requirements[0].title = "stale local value"
        planning["requirements"][0]["title"] = "Updated API login error"
        RequirementService().save_requirements(
            self.db,
            self.project.project_id,
            planning["requirements"],
        )
        self.assertEqual(
            self.db.scalars(select(Requirement)).all()[0].title,
            "Updated API login error",
        )
        self.assertEqual(
            len(self.db.scalars(select(Requirement)).all()), 1
        )

        member = Member(
            employee_no="M-1",
            name="Backend Member",
            primary_role="BACKEND",
            career_level="SENIOR",
            employment_status="ACTIVE",
        )
        self.db.add(member)
        self.db.commit()
        self.db.add_all(
            [
                MemberSkill(
                    member_id=member.member_id,
                    skill_name="api",
                    proficiency_level="HIGH",
                    experience_years=5,
                ),
                MemberWorkload(
                    member_id=member.member_id,
                    recorded_date=date(2026, 7, 28),
                    assigned_task_count=1,
                    available_hours=40,
                    workload_rate=10,
                ),
            ]
        )
        self.db.commit()

        assignments = AssignmentAgent().assign(
            self.db, self.project.project_id
        )
        self.assertEqual(len(assignments), 4)
        self.assertTrue(
            all(item["assignee"] == "Backend Member" for item in assignments)
        )

        schedules = ScheduleService().create_schedule(
            self.db, self.project.project_id, date(2026, 8, 3)
        )
        self.assertEqual(len(schedules), 4)
        self.assertEqual(schedules[0].assignee, "Backend Member")
        self.assertLess(
            schedules[0].planned_end_date, schedules[1].planned_start_date
        )

        impact = RequirementImpactService().evaluate(
            self.db,
            self.project.project_id,
            requirements[0].requirement_id,
            "SCOPE",
            "Expand login",
        )
        self.assertEqual(impact["impact"]["affected_wbs_count"], 4)
        self.assertEqual(impact["impact"]["affected_schedule_count"], 4)
        self.assertEqual(impact["affected_assignees"], ["Backend Member"])

        risk_output = RiskAgent().analyze(risk_context)
        saved_risks = RiskService().save_risks(
            self.db, self.project.project_id, risk_output["risks"]
        )
        self.assertEqual(len(saved_risks), 1)
        risk_output["risks"][0]["risk_title"] = "Updated risk"
        RiskService().save_risks(
            self.db, self.project.project_id, risk_output["risks"]
        )
        self.assertEqual(len(self.db.scalars(select(Risk)).all()), 1)
        self.assertEqual(
            self.db.scalars(select(Risk)).first().risk_title,
            "Updated risk",
        )

        report = ReportAgent().generate(report_context)
        self.assertEqual(report["total_events"], 1)
        self.assertEqual(report["in_progress_count"], 1)

    def test_reassignment_updates_task_and_related_schedule(self):
        requirement = Requirement(
            project_id=self.project.project_id,
            requirement_code="REQ-1",
            title="API",
            requirement_type="FUNCTIONAL",
            priority="HIGH",
            status="ACTIVE",
        )
        self.db.add(requirement)
        self.db.commit()
        task = WBS(
            project_id=self.project.project_id,
            requirement_id=requirement.requirement_id,
            task_name="Spring API implementation",
            task_description="Build Spring Boot API",
            task_order=1,
            estimated_days=2,
            assignee="Current Member",
            status="TODO",
        )
        current = Member(
            employee_no="M-1",
            name="Current Member",
            primary_role="BACKEND",
            career_level="JUNIOR",
            employment_status="ACTIVE",
        )
        candidate = Member(
            employee_no="M-2",
            name="New Member",
            primary_role="BACKEND",
            career_level="SENIOR",
            employment_status="ACTIVE",
        )
        self.db.add_all([task, current, candidate])
        self.db.commit()
        schedule = Schedule(
            project_id=self.project.project_id,
            wbs_id=task.wbs_id,
            assignee="Current Member",
            planned_start_date=date(2026, 8, 3),
            planned_end_date=date(2026, 8, 4),
            status="PLANNED",
        )
        self.db.add_all(
            [
                schedule,
                MemberSkill(
                    member_id=candidate.member_id,
                    skill_name="Spring Boot",
                    proficiency_level="HIGH",
                    experience_years=4,
                ),
                MemberWorkload(
                    member_id=candidate.member_id,
                    recorded_date=date(2026, 7, 28),
                    assigned_task_count=0,
                    available_hours=40,
                    workload_rate=0,
                ),
            ]
        )
        self.db.commit()

        result = ReassignmentService().reassign(
            self.db,
            self.project.project_id,
            task.wbs_id,
            "Current owner unavailable",
        )

        self.assertEqual(result["reassignment_status"], "COMPLETED")
        self.assertEqual(result["new_assignee"], "New Member")
        self.assertTrue(result["schedule_updated"])
        self.assertEqual(task.assignee, "New Member")
        self.assertEqual(schedule.assignee, "New Member")

    def test_context_and_impact_missing_records_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "프로젝트"):
            ContextBuilder().build_common_context(self.db, 999)
        with self.assertRaisesRegex(ValueError, "요구사항"):
            RequirementImpactService().evaluate(
                self.db, self.project.project_id, 999, "SCOPE", "missing"
            )


if __name__ == "__main__":
    unittest.main()
