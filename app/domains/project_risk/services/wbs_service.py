from sqlalchemy.orm import Session

from ..models.requirement import Requirement
from ..models.wbs import WBS


class WBSService:

    def save_wbs_tasks(
        self,
        db: Session,
        project_id: int,
        wbs_tasks: list[dict],
    ) -> list[WBS]:

        saved_tasks = []

        try:
            for item in wbs_tasks:
                requirement = (
                    db.query(Requirement)
                    .filter(
                        Requirement.project_id == project_id,
                        Requirement.requirement_code
                        == item["requirement_code"],
                    )
                    .first()
                )

                if requirement is None:
                    raise ValueError(
                        "연결할 요구사항을 찾을 수 없습니다: "
                        f"{item['requirement_code']}"
                    )

                existing = (
                    db.query(WBS)
                    .filter(
                        WBS.project_id == project_id,
                        WBS.requirement_id
                        == requirement.requirement_id,
                        WBS.task_order
                        == item["task_order"],
                    )
                    .first()
                )

                if existing:
                    existing.task_name = item["task_name"]
                    existing.task_description = item.get(
                        "task_description"
                    )
                    existing.estimated_days = item.get(
                        "estimated_days",
                        1,
                    )
                    existing.status = item.get(
                        "status",
                        "TODO",
                    )

                    saved_tasks.append(existing)
                    continue

                task = WBS(
                    project_id=project_id,
                    requirement_id=
                        requirement.requirement_id,
                    task_name=item["task_name"],
                    task_description=item.get(
                        "task_description"
                    ),
                    task_order=item["task_order"],
                    estimated_days=item.get(
                        "estimated_days",
                        1,
                    ),
                    status=item.get(
                        "status",
                        "TODO",
                    ),
                )

                db.add(task)
                saved_tasks.append(task)

            db.commit()

            for task in saved_tasks:
                db.refresh(task)

            return saved_tasks

        except Exception:
            db.rollback()
            raise
