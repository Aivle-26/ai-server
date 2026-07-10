from pprint import pprint

import app.models

from app.agents.planning_agent import PlanningAgent
from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder
from app.services.requirement_service import RequirementService
from app.services.wbs_service import WBSService


def main() -> None:
    db = SessionLocal()

    builder = ContextBuilder()
    planner = PlanningAgent()
    requirement_service = RequirementService()
    wbs_service = WBSService()

    try:
        planning_context = (
            builder.build_planning_context(
                db=db,
                project_id=1,
            )
        )

        planning_result = planner.analyze(
            planning_context=planning_context
        )

        requirement_service.save_requirements(
            db=db,
            project_id=1,
            requirements=
                planning_result["requirements"],
        )

        saved_tasks = wbs_service.save_wbs_tasks(
            db=db,
            project_id=1,
            wbs_tasks=planning_result["wbs_tasks"],
        )

        print("===== WBS 저장 완료 =====")
        print("저장된 업무 수:", len(saved_tasks))

        for task in saved_tasks:
            pprint(
                {
                    "wbs_id": task.wbs_id,
                    "requirement_id":
                        task.requirement_id,
                    "task_order": task.task_order,
                    "task_name": task.task_name,
                    "estimated_days":
                        task.estimated_days,
                    "status": task.status,
                }
            )

    except Exception as error:
        print("===== WBS 저장 실패 =====")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()