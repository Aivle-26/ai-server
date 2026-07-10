from sqlalchemy.orm import Session

from app.models.normalized_event import NormalizedEvent


class EventService:

    def save_event(
        self,
        db: Session,
        project_id: int,
        raw_data_id: int,
        normalized_data: dict,
    ) -> NormalizedEvent:

        event = NormalizedEvent(
            project_id=project_id,
            raw_data_id=raw_data_id,
            source_type=normalized_data["source_type"],
            event_type=normalized_data["event_type"],
            title=normalized_data.get("title"),
            content=normalized_data.get("content"),
            status=normalized_data.get("status"),
            priority=normalized_data.get("priority"),
            actor_external_id=normalized_data.get("actor_external_id"),
            occurred_at=normalized_data.get("occurred_at"),
            metadata_json=normalized_data.get("metadata_json"),
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        return event