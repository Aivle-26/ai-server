from datetime import datetime
from typing import Any

from .base import BaseAdapter


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


class GitHubAdapter(BaseAdapter):

    def normalize(
        self,
        payload: dict[str, Any]
    ) -> dict:
        data_type = str(
            payload.get("data_type", "")
        ).upper()

        data = payload.get("data", payload)

        if data_type == "ISSUE":
            return self._normalize_issue(data)

        if data_type in {"PULL_REQUEST", "PR"}:
            return self._normalize_pull_request(data)

        if data_type == "COMMIT":
            return self._normalize_commit(data)

        raise ValueError(
            f"지원하지 않는 GitHub 데이터 유형입니다: {data_type}"
        )

    def _normalize_issue(
        self,
        data: dict[str, Any]
    ) -> dict:
        user = data.get("user") or {}

        return {
            "source_type": "GITHUB",
            "event_type": "ISSUE",
            "title": data.get("title"),
            "content": data.get("body"),
            "status": (
                str(data.get("state")).upper()
                if data.get("state")
                else None
            ),
            "priority": self._extract_priority(
                data.get("labels", [])
            ),
            "actor_external_id": (
                str(user.get("id"))
                if user.get("id") is not None
                else user.get("login")
            ),
            "occurred_at": parse_datetime(
                data.get("created_at")
            ),
            "metadata_json": {
                "issue_number": data.get("number"),
                "labels": [
                    label.get("name")
                    for label in data.get("labels", [])
                    if isinstance(label, dict)
                ],
                "html_url": data.get("html_url"),
                "updated_at": data.get("updated_at"),
                "closed_at": data.get("closed_at"),
            },
        }

    def _normalize_pull_request(
        self,
        data: dict[str, Any]
    ) -> dict:
        user = data.get("user") or {}
        base = data.get("base") or {}
        head = data.get("head") or {}

        status = "MERGED" if data.get("merged") else data.get("state")

        return {
            "source_type": "GITHUB",
            "event_type": "PULL_REQUEST",
            "title": data.get("title"),
            "content": data.get("body"),
            "status": (
                str(status).upper()
                if status
                else None
            ),
            "priority": None,
            "actor_external_id": (
                str(user.get("id"))
                if user.get("id") is not None
                else user.get("login")
            ),
            "occurred_at": parse_datetime(
                data.get("created_at")
            ),
            "metadata_json": {
                "pr_number": data.get("number"),
                "base_branch": base.get("ref"),
                "head_branch": head.get("ref"),
                "merged": data.get("merged", False),
                "merged_at": data.get("merged_at"),
                "html_url": data.get("html_url"),
            },
        }

    def _normalize_commit(
        self,
        data: dict[str, Any]
    ) -> dict:
        commit = data.get("commit") or {}
        author = commit.get("author") or {}

        return {
            "source_type": "GITHUB",
            "event_type": "COMMIT",
            "title": commit.get("message"),
            "content": commit.get("message"),
            "status": "COMPLETED",
            "priority": None,
            "actor_external_id": (
                author.get("email")
                or author.get("name")
            ),
            "occurred_at": parse_datetime(
                author.get("date")
            ),
            "metadata_json": {
                "sha": data.get("sha"),
                "html_url": data.get("html_url"),
            },
        }

    def _extract_priority(
        self,
        labels: list[Any]
    ) -> str | None:
        label_names = {
            str(label.get("name", "")).lower()
            for label in labels
            if isinstance(label, dict)
        }

        if {"critical", "urgent", "blocker"} & label_names:
            return "CRITICAL"

        if {"high", "priority-high"} & label_names:
            return "HIGH"

        if {"medium", "priority-medium"} & label_names:
            return "MEDIUM"

        if {"low", "priority-low"} & label_names:
            return "LOW"

        return None
