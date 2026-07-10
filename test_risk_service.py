from pprint import pprint

import app.models

from app.agents.risk_agent import RiskAgent
from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder
from app.services.risk_service import RiskService


def main() -> None:
    db = SessionLocal()

    builder = ContextBuilder()
    agent = RiskAgent()
    service = RiskService()

    try:
        risk_context = builder.build_risk_context(
            db=db,
            project_id=1,
        )

        result = agent.analyze(
            risk_context=risk_context,
        )

        saved_risks = service.save_risks(
            db=db,
            project_id=1,
            risks=result["risks"],
        )

        print("===== 리스크 저장 완료 =====")
        print("저장된 리스크 수:", len(saved_risks))

        for risk in saved_risks:
            pprint(
                {
                    "risk_id": risk.risk_id,
                    "risk_code": risk.risk_code,
                    "risk_type": risk.risk_type,
                    "risk_title": risk.risk_title,
                    "risk_level": risk.risk_level,
                    "source": risk.detection_source,
                    "actions": risk.recommended_actions,
                }
            )

    except Exception as error:
        print("===== 리스크 저장 실패 =====")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()