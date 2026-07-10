from pprint import pprint

from app.adapters.github_adapter import GitHubAdapter


adapter = GitHubAdapter()

github_issue = {
    "data_type": "ISSUE",
    "data": {
        "id": 101,
        "number": 12,
        "title": "로그인 API 오류",
        "body": "토큰 만료 시 500 에러가 발생합니다.",
        "state": "open",
        "user": {
            "id": 100,
            "login": "kim"
        },
        "labels": [
            {
                "name": "high"
            }
        ],
        "created_at": "2026-07-10T09:00:00Z",
        "updated_at": "2026-07-10T10:00:00Z",
        "html_url": "https://github.com/test/repo/issues/12"
    }
}

result = adapter.normalize(github_issue)

print("=== 변환 결과 ===")
pprint(result)