from sqlalchemy.orm import Session

from app.models.risk import Risk


class RiskService:

    def save_risks(
        self,
        db: Session,
        project_id: int,
        risks: list[dict],
    ) -> list[Risk]:

        saved_risks = []

        try:
            for item in risks:
                source_event_id = item.get("source_event_id")

                existing = (
                    db.query(Risk)
                    .filter(
                        Risk.project_id == project_id,
                        Risk.source_event_id == source_event_id,
                    )
                    .first()
                )

                if existing:
                    existing.risk_code = item["risk_code"]
                    existing.risk_type = item["risk_type"]
                    existing.risk_title = item["risk_title"]
                    existing.risk_description = item.get(
                        "risk_description"
                    )
                    existing.probability_score = item[
                        "probability_score"
                    ]
                    existing.impact_score = item["impact_score"]
                    existing.risk_level = item["risk_level"]
                    existing.status = item.get("status", "OPEN")
                    existing.detection_source = item.get(
                        "detection_source"
                    )
                    existing.evidence_text = item.get(
                        "evidence_text"
                    )
                    existing.recommended_actions = item.get(
                        "recommended_actions"
                    )

                    saved_risks.append(existing)
                    continue

                risk = Risk(
                    project_id=project_id,
                    source_event_id=source_event_id,
                    risk_code=item["risk_code"],
                    risk_type=item["risk_type"],
                    risk_title=item["risk_title"],
                    risk_description=item.get(
                        "risk_description"
                    ),
                    probability_score=item[
                        "probability_score"
                    ],
                    impact_score=item["impact_score"],
                    risk_level=item["risk_level"],
                    status=item.get("status", "OPEN"),
                    detection_source=item.get(
                        "detection_source"
                    ),
                    evidence_text=item.get(
                        "evidence_text"
                    ),
                    recommended_actions=item.get(
                        "recommended_actions"
                    ),
                )

                db.add(risk)
                saved_risks.append(risk)

            db.commit()

            for risk in saved_risks:
                db.refresh(risk)

            return saved_risks

        except Exception:
            db.rollback()
            raise