from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


REQUEST_KEYWORDS = ("확인", "질문", "요청", "검토", "부탁", "문의", "help", "review")
CONTEXT_KEYWORDS = ("긴급", "blocker", "막혔", "오류", "에러", "장애", "결정 대기", "마감", "지연")
ACK_REACTIONS = ("white_check_mark", "eyes", "check", "확인", "승인", "처리완료")


@dataclass(frozen=True)
class SlackMessage:
    channel_id: str
    channel_name: str
    message_ts: datetime
    thread_ts: str | None
    user_id: str
    message_text: str
    reply_count: int
    mention_count: int
    reaction_summary: str
    file_count: int


def _to_naive_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class CommunicationRiskService:
    """Extracts only the facts needed for a simple project communication risk."""

    def build_facts(
        self,
        raw_messages: list[dict[str, Any]],
        analysis_end: datetime | str,
    ) -> dict[str, Any]:
        end = _to_naive_datetime(analysis_end)
        recent_start = end - timedelta(days=7)
        previous_start = recent_start - timedelta(days=7)
        messages = self._normalize(raw_messages)
        recent = [message for message in messages if recent_start <= message.message_ts < end]
        previous = [message for message in messages if previous_start <= message.message_ts < recent_start]

        previous_count = len(previous)
        recent_count = len(recent)
        activity_change_percent = (
            round(((recent_count - previous_count) / previous_count) * 100, 1)
            if previous_count
            else None
        )
        activity_drop = previous_count >= 5 and recent_count <= previous_count * 0.5

        candidates = []
        long_unanswered_count = 0
        for message in recent:
            age_hours = round((end - message.message_ts).total_seconds() / 3600, 1)
            request_like = self._is_request(message)
            context_like = self._has_context_keyword(message.message_text)
            unanswered = (
                request_like
                and message.reply_count == 0
                and not self._has_acknowledgement(message.reaction_summary)
                and age_hours >= 24
            )
            if unanswered:
                long_unanswered_count += 1
            if unanswered or context_like:
                candidates.append({
                    **self._evidence(message),
                    "age_hours": age_hours,
                    "is_long_unanswered": unanswered,
                    "is_request_like": request_like,
                    "has_context_keyword": context_like,
                })

        candidates.sort(
            key=lambda item: (item["is_long_unanswered"], item["age_hours"]),
            reverse=True,
        )
        return {
            "analysis_window": {
                "start": recent_start.isoformat(),
                "end": end.isoformat(),
            },
            "metrics": {
                "recent_7d_message_count": recent_count,
                "previous_7d_message_count": previous_count,
                "activity_change_percent": activity_change_percent,
                "long_unanswered_count": long_unanswered_count,
            },
            "activity_drop": activity_drop,
            "candidate_messages": candidates[:10],
        }

    def fallback_decision(self, facts: dict[str, Any]) -> dict[str, Any]:
        metrics = facts["metrics"]
        candidates = facts["candidate_messages"]
        long_unanswered = metrics["long_unanswered_count"]
        context_unanswered = any(
            item["is_long_unanswered"] and item["has_context_keyword"]
            for item in candidates
        )

        if context_unanswered or (facts["activity_drop"] and long_unanswered):
            level = "HIGH"
        elif facts["activity_drop"] or long_unanswered:
            level = "MEDIUM"
        else:
            level = "LOW"

        reasons = []
        if facts["activity_drop"]:
            reasons.append(
                f"최근 7일 대화량이 이전 7일 대비 {abs(metrics['activity_change_percent']):.1f}% 감소했습니다."
            )
        if long_unanswered:
            reasons.append(f"질문 또는 멘션 메시지 {long_unanswered}건이 24시간 이상 미응답입니다.")
        if context_unanswered:
            reasons.append("오류·차단·일정 우려 맥락의 메시지가 장기 미응답 상태입니다.")
        if not reasons:
            reasons.append("대화량과 응답 상태에서 유의미한 위험 신호가 탐지되지 않았습니다.")

        actions = {
            "HIGH": "담당자에게 즉시 상태 확인을 요청하고, 프로젝트 일정 영향 여부를 검토하세요.",
            "MEDIUM": "미응답 스레드와 최근 업무 진행 상태를 확인하세요.",
            "LOW": "현재 협업 상태를 유지하며 정기적으로 대화량과 미응답 스레드를 확인하세요.",
        }
        return {
            "communication_risk_level": level,
            "reasons": reasons[:3],
            "evidence_message_ts": [item["message_ts"] for item in candidates[:3]],
            "recommended_action": actions[level],
        }

    def build_response(
        self,
        project_id: int,
        project_name: str | None,
        facts: dict[str, Any],
        decision: dict[str, Any],
        llm_status: str,
    ) -> dict[str, Any]:
        candidate_by_ts = {
            item["message_ts"]: item
            for item in facts["candidate_messages"]
        }
        evidence = [
            candidate_by_ts[message_ts]
            for message_ts in decision["evidence_message_ts"]
            if message_ts in candidate_by_ts
        ]
        return {
            "project_id": project_id,
            "project_name": project_name,
            **decision,
            "evidence_messages": [
                {
                    "channel_id": item["channel_id"],
                    "channel_name": item["channel_name"],
                    "message_ts": item["message_ts"],
                    "thread_ts": item["thread_ts"],
                    "message_text": item["message_text"],
                }
                for item in evidence
            ],
            "metrics": facts["metrics"],
            "analysis_window": facts["analysis_window"],
            "llm_status": llm_status,
        }

    def _normalize(self, raw_messages: list[dict[str, Any]]) -> list[SlackMessage]:
        return sorted([
            SlackMessage(
                channel_id=item["channel_id"],
                channel_name=item["channel_name"],
                message_ts=_to_naive_datetime(item["message_ts"]),
                thread_ts=item.get("thread_ts"),
                user_id=item["user_id"],
                message_text=item["message_text"],
                reply_count=int(item.get("reply_count", 0)),
                mention_count=int(item.get("mention_count", 0)),
                reaction_summary=item.get("reaction_summary", ""),
                file_count=int(item.get("file_count", 0)),
            )
            for item in raw_messages
        ], key=lambda message: message.message_ts)

    def _is_request(self, message: SlackMessage) -> bool:
        lowered = message.message_text.lower()
        return (
            message.mention_count > 0
            or "?" in message.message_text
            or any(keyword in lowered for keyword in REQUEST_KEYWORDS)
        )

    def _has_context_keyword(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in CONTEXT_KEYWORDS)

    def _has_acknowledgement(self, reaction_summary: str) -> bool:
        lowered = reaction_summary.lower()
        return any(reaction in lowered for reaction in ACK_REACTIONS)

    def _evidence(self, message: SlackMessage) -> dict[str, Any]:
        return {
            "channel_id": message.channel_id,
            "channel_name": message.channel_name,
            "message_ts": message.message_ts.isoformat(),
            "thread_ts": message.thread_ts,
            "message_text": message.message_text,
        }
