from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.external_data import ExternalRawData
from app.services.event_service import EventService
from app.services.normalization_service import NormalizationService


class IngestionService:
    def __init__(self) -> None:
        self.normalization_service = NormalizationService()
        self.event_service = EventService()

    def process(
        self,
        db: Session,
        project_id: int,
        source_type: str,
        data_type: str,
        external_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_data = ExternalRawData(
            project_id=project_id,
            source_type=source_type.upper(),
            data_type=data_type.upper(),
            external_id=external_id,
            payload=payload,
            processing_status="RECEIVED",
        )

        db.add(raw_data)
        db.commit()
        db.refresh(raw_data)

        try:
            adapter_payload = {
                "data_type": data_type.upper(),
                "data": payload,
            }

            normalized_data = self.normalization_service.normalize(
                source_type=source_type,
                payload=adapter_payload,
            )

            event = self.event_service.save_event(
                db=db,
                project_id=project_id,
                raw_data_id=raw_data.raw_data_id,
                normalized_data=normalized_data,
            )

            raw_data.processing_status = "NORMALIZED"

            if hasattr(raw_data, "normalized_at"):
                raw_data.normalized_at = datetime.utcnow()

            db.commit()
            db.refresh(raw_data)

            return {
                "raw_data_id": raw_data.raw_data_id,
                "normalized_event_id": event.normalized_event_id,
                "processing_status": raw_data.processing_status,
                "normalized_data": normalized_data,
            }

        except Exception as error:
            raw_data.processing_status = "FAILED"
            raw_data.processing_error = str(error)

            db.commit()
            db.refresh(raw_data)

            raise