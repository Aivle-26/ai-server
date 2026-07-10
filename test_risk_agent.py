from pprint import pprint

import app.models

from app.agents.risk_agent import RiskAgent
from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder


def main() -> None:
    db = SessionLocal()
    builder = ContextBuilder()
    agent = RiskAgent()

    try:
        risk_context = builder.build_risk_context(
            db=db,
            project_id=1,
        )

        result = agent.analyze(
            risk_context=risk_context
        )

        print("===== Risk Agent 결과 =====")
        pprint(result)

    except Exception as error:
        print("===== Risk Agent 실행 실패 =====")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()