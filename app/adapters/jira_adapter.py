from datetime import datetime
from typing import Any

from app.adapters.base import BaseAdapter


def parse_jira_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


class JiraAdapter(BaseAdapter):

    def normalize(
        self,
        payload: dict[str, Any]
    ) -> dict:
        data_type = str(
            payload.get("data_type", "")
        ).upper()

        data = payload.get("data", payload)

        if data_type in {
            "EPIC",
            "STORY",
            "TASK",
            "BUG",
            "ISSUE",
        }:
            return self._normalize_issue(
                data=data,
                data_type=data_type,
            )

        raise ValueError(
            f"지원하지 않는 Jira 데이터 유형입니다: {data_type}"
        )

    def _normalize_issue(
        self,
        data: dict[str, Any],
        data_type: str,
    ) -> dict:
        fields = data.get("fields") or {}

        assignee = fields.get("assignee") or {}
        status = fields.get("status") or {}
        priority = fields.get("priority") or {}

        return {
            "source_type": "JIRA",
            "event_type": data_type,
            "title": fields.get("summary"),
            "content": fields.get("description"),
            "status": (
                str(status.get("name")).upper()
                if status.get("name")
                else None
            ),
            "priority": self._normalize_priority(
                priority.get("name")
            ),
            "actor_external_id": (
                assignee.get("accountId")
                or assignee.get("name")
            ),
            "occurred_at": parse_jira_datetime(
                fields.get("created")
            ),
            "metadata_json": {
                "jira_key": data.get("key"),
                "issue_id": data.get("id"),
                "issue_type": data_type,
                "due_date": fields.get("duedate"),
                "story_points": fields.get("story_points"),
                "updated_at": fields.get("updated"),
                "resolution": (
                    fields.get("resolution", {}).get("name")
                    if fields.get("resolution")
                    else None
                ),
            },
        }

    def _normalize_priority(
        self,
        value: str | None,
    ) -> str | None:
        if not value:
            return None

        normalized = value.upper()

        priority_map = {
            "HIGHEST": "CRITICAL",
            "CRITICAL": "CRITICAL",
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW",
            "LOWEST": "LOW",
        }

        return priority_map.get(normalized, normalized)