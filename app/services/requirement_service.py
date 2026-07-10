from sqlalchemy.orm import Session

from app.models.requirement import Requirement


class RequirementService:

    def save_requirements(
        self,
        db: Session,
        project_id: int,
        requirements: list[dict],
    ) -> list[Requirement]:

        saved_requirements = []

        try:
            for item in requirements:
                source_event_id = item.get("source_event_id")

                existing = (
                    db.query(Requirement)
                    .filter(
                        Requirement.project_id == project_id,
                        Requirement.source_event_id == source_event_id,
                    )
                    .first()
                )

                if existing:
                    existing.requirement_code = item[
                        "requirement_code"
                    ]
                    existing.title = item["title"]
                    existing.description = item.get(
                        "description"
                    )
                    existing.requirement_type = item[
                        "requirement_type"
                    ]
                    existing.priority = item["priority"]
                    existing.status = item["status"]
                    existing.acceptance_criteria = item.get(
                        "acceptance_criteria"
                    )
                    existing.source_type = item.get(
                        "source_type"
                    )

                    saved_requirements.append(existing)
                    continue

                requirement = Requirement(
                    project_id=project_id,
                    source_event_id=source_event_id,
                    requirement_code=item[
                        "requirement_code"
                    ],
                    title=item["title"],
                    description=item.get("description"),
                    requirement_type=item[
                        "requirement_type"
                    ],
                    priority=item["priority"],
                    status=item["status"],
                    acceptance_criteria=item.get(
                        "acceptance_criteria"
                    ),
                    source_type=item.get("source_type"),
                )

                db.add(requirement)
                saved_requirements.append(requirement)

            db.commit()

            for requirement in saved_requirements:
                db.refresh(requirement)

            return saved_requirements

        except Exception:
            db.rollback()
            raise