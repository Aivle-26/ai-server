from datetime import date
from pprint import pprint

import app.models

from app.core.database import SessionLocal
from app.services.schedule_service import ScheduleService


def main():

    db = SessionLocal()

    service = ScheduleService()

    schedules = service.create_schedule(
        db=db,
        project_id=1,
        start_date=date(2026, 7, 13),
    )

    print("===== 일정 생성 완료 =====")

    for item in schedules:

        pprint(
            {
                "schedule_id": item.schedule_id,
                "wbs_id": item.wbs_id,
                "assignee": item.assignee,
                "start": item.planned_start_date,
                "end": item.planned_end_date,
                "status": item.status,
            }
        )

    db.close()


if __name__ == "__main__":
    main()