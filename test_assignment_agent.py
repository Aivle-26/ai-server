from pprint import pprint

import app.models

from app.agents.assignment_agent import AssignmentAgent
from app.core.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    agent = AssignmentAgent()

    try:
        result = agent.assign(
            db=db,
            project_id=1,
        )

        print("===== 담당자 추천 결과 =====")

        for item in result:
            pprint(item)

    except Exception as error:
        print("===== 담당자 추천 실패 =====")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()