from app.models.project import Project
from app.models.external_data import ExternalRawData
from app.models.normalized_event import NormalizedEvent
from pprint import pprint

from app.core.database import SessionLocal
from app.services.ingestion_service import IngestionService


def main() -> None:
    db = SessionLocal()
    service = IngestionService()

    github_issue = {
        "id": 101,
        "number": 12,
        "title": "로그인 API 오류",
        "body": "토큰 만료 시 500 에러가 발생합니다.",
        "state": "open",
        "user": {
            "id": 100,
            "login": "kim",
        },
        "labels": [
            {
                "name": "high",
            }
        ],
        "created_at": "2026-07-10T09:00:00Z",
        "updated_at": "2026-07-10T10:00:00Z",
        "html_url": "https://github.com/test/repo/issues/12",
    }

    try:
        result = service.process(
            db=db,
            project_id=1,
            source_type="GITHUB",
            data_type="ISSUE",
            external_id="github-issue-12",
            payload=github_issue,
        )

        print("=== 데이터 처리 완료 ===")
        pprint(result)

    except Exception as error:
        print("=== 데이터 처리 실패 ===")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()