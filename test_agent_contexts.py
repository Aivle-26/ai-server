from pprint import pprint

import app.models

from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder


def main() -> None:
    db = SessionLocal()
    builder = ContextBuilder()

    try:
        planning_context = (
            builder.build_planning_context(
                db=db,
                project_id=1,
            )
        )

        report_context = (
            builder.build_report_context(
                db=db,
                project_id=1,
            )
        )

        risk_context = (
            builder.build_risk_context(
                db=db,
                project_id=1,
            )
        )

        print("\n=== Planning Context ===")
        pprint(planning_context)

        print("\n=== Report Context ===")
        pprint(report_context)

        print("\n=== Risk Context ===")
        pprint(risk_context)

    except Exception as error:
        print("=== Context 생성 실패 ===")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()