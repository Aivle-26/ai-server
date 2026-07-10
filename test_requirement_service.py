from pprint import pprint

import app.models

from app.agents.planning_agent import PlanningAgent
from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder
from app.services.requirement_service import RequirementService


def main():

    db = SessionLocal()

    builder = ContextBuilder()

    planner = PlanningAgent()

    requirement_service = RequirementService()

    planning_context = builder.build_planning_context(
        db=db,
        project_id=1,
    )

    planning_result = planner.analyze(
        planning_context
    )

    saved = requirement_service.save_requirements(
        db=db,
        project_id=1,
        requirements=planning_result["requirements"],
    )

    print("===== 저장 완료 =====")

    for requirement in saved:

        pprint(
            {
                "id": requirement.requirement_id,
                "code": requirement.requirement_code,
                "title": requirement.title,
                "priority": requirement.priority,
                "type": requirement.requirement_type,
            }
        )

    db.close()


if __name__ == "__main__":
    main()