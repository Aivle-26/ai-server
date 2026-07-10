from pprint import pprint

import app.models

from app.core.database import SessionLocal
from app.services.ingestion_service import IngestionService


db = SessionLocal()

service = IngestionService()

slack_message = {
    "channel": "backend",
    "user": "U001",
    "text": "긴급 로그인 API 오류가 발생했습니다.",
    "ts": "1783663200.000000",
    "reply_count": 2,
    "reactions": [
        {
            "name": "warning",
            "count": 3
        }
    ]
}

result = service.process(
    db=db,
    project_id=1,
    source_type="SLACK",
    data_type="MESSAGE",
    external_id="slack-msg-001",
    payload=slack_message,
)

print("=== Slack 처리 완료 ===")
pprint(result)
