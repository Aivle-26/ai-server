from pprint import pprint

import app.models

from app.core.database import SessionLocal
from app.services.ingestion_service import IngestionService


def main() -> None:
    db = SessionLocal()
    service = IngestionService()

    jira_task = {
        "id": "10001",
        "key": "AIP-101",
        "fields": {
            "summary": "로그인 API 오류 수정",
            "description": "토큰 만료 시 발생하는 500 오류를 수정합니다.",
            "status": {
                "name": "In Progress"
            },
            "priority": {
                "name": "High"
            },
            "assignee": {
                "accountId": "jira-user-001",
                "displayName": "Backend Developer"
            },
            "created": "2026-07-10T08:30:00Z",
            "updated": "2026-07-10T11:00:00Z",
            "duedate": "2026-07-15",
            "story_points": 5,
            "resolution": None
        }
    }

    try:
        result = service.process(
            db=db,
            project_id=1,
            source_type="JIRA",
            data_type="TASK",
            external_id="AIP-101",
            payload=jira_task,
        )

        print("=== Jira 처리 완료 ===")
        pprint(result)

    except Exception as error:
        print("=== Jira 처리 실패 ===")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()