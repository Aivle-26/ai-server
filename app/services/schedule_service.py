from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.schedule import Schedule
from app.models.wbs import WBS


class ScheduleService:

    def create_schedule(
        self,
        db: Session,
        project_id: int,
        start_date: date,
    ) -> list[Schedule]:

        tasks = (
            db.query(WBS)
            .filter(
                WBS.project_id == project_id
            )
            .order_by(
                WBS.requirement_id,
                WBS.task_order,
            )
            .all()
        )

        current_date = start_date

        schedules = []

        for task in tasks:

            duration = max(
                1,
                task.estimated_days,
            )

            planned_start = current_date

            planned_end = (
                planned_start
                + timedelta(days=duration - 1)
            )

            existing = (
                db.query(Schedule)
                .filter(
                    Schedule.wbs_id == task.wbs_id
                )
                .first()
            )

            if existing:

                existing.assignee = task.assignee
                existing.planned_start_date = planned_start
                existing.planned_end_date = planned_end

                schedules.append(existing)

            else:

                schedule = Schedule(
                    project_id=project_id,
                    wbs_id=task.wbs_id,
                    assignee=task.assignee,
                    planned_start_date=planned_start,
                    planned_end_date=planned_end,
                    status="PLANNED",
                )

                db.add(schedule)

                schedules.append(schedule)

            current_date = (
                planned_end
                + timedelta(days=1)
            )

        db.commit()

        for schedule in schedules:
            db.refresh(schedule)

        return schedules