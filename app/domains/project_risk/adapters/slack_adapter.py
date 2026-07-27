from datetime import datetime
from typing import Any

from .base import BaseAdapter


def parse_slack_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromtimestamp(float(value))
    except (TypeError, ValueError):
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )


class SlackAdapter(BaseAdapter):

    def normalize(
        self,
        payload: dict[str, Any]
    ) -> dict:
        data_type = str(
            payload.get("data_type", "")
        ).upper()

        data = payload.get("data", payload)

        if data_type in {"MESSAGE", "THREAD_REPLY"}:
            return self._normalize_message(data, data_type)

        raise ValueError(
            f"지원하지 않는 Slack 데이터 유형입니다: {data_type}"
        )

    def _normalize_message(
        self,
        data: dict[str, Any],
        data_type: str,
    ) -> dict:
        message_ts = data.get("ts")
        thread_ts = data.get("thread_ts")

        return {
            "source_type": "SLACK",
            "event_type": (
                "THREAD_REPLY"
                if data_type == "THREAD_REPLY" or thread_ts
                else "MESSAGE"
            ),
            "title": self._make_title(data.get("text")),
            "content": data.get("text"),
            "status": "SENT",
            "priority": self._extract_priority(
                data.get("text")
            ),
            "actor_external_id": data.get("user"),
            "occurred_at": parse_slack_datetime(message_ts),
            "metadata_json": {
                "channel_id": data.get("channel"),
                "message_ts": message_ts,
                "thread_ts": thread_ts,
                "reply_count": data.get("reply_count", 0),
                "reactions": data.get("reactions", []),
                "files": data.get("files", []),
            },
        }

    def _make_title(
        self,
        text: str | None
    ) -> str | None:
        if not text:
            return None

        text = text.strip()

        if len(text) <= 50:
            return text

        return f"{text[:50]}..."

    def _extract_priority(
        self,
        text: str | None
    ) -> str | None:
        if not text:
            return None

        lowered = text.lower()

        critical_keywords = [
            "긴급",
            "즉시",
            "장애",
            "서비스 중단",
            "critical",
            "urgent",
            "blocker",
        ]

        high_keywords = [
            "지연",
            "마감",
            "오류",
            "에러",
            "실패",
            "high priority",
        ]

        if any(
            keyword in lowered
            for keyword in critical_keywords
        ):
            return "CRITICAL"

        if any(
            keyword in lowered
            for keyword in high_keywords
        ):
            return "HIGH"

        return None
