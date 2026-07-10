from pprint import pprint

import app.models

from app.agents.planning_agent import PlanningAgent
from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder


def main() -> None:
    db = SessionLocal()
    builder = ContextBuilder()
    agent = PlanningAgent()

    try:
        planning_context = (
            builder.build_planning_context(
                db=db,
                project_id=1,
            )
        )

        result = agent.analyze(
            planning_context=planning_context
        )

        print("=== Planning Agent 결과 ===")
        pprint(result)

    except Exception as error:
        print("=== Planning Agent 실행 실패 ===")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()