from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SlackMessageThreadInput(BaseModel):
    """One row from the slack_message_thread data definition."""

    channel_id: str = Field(min_length=1)
    channel_name: str = Field(min_length=1)
    message_ts: datetime
    thread_ts: str | None = None
    user_id: str = Field(min_length=1)
    message_text: str = Field(min_length=1)
    reply_count: int = Field(default=0, ge=0)
    mention_count: int = Field(default=0, ge=0)
    reaction_summary: str = ""
    file_count: int = Field(default=0, ge=0)


class CommunicationRiskRequest(BaseModel):
    project_id: int = Field(gt=0)
    project_name: str | None = None
    analysis_end: datetime | None = None
    messages: list[SlackMessageThreadInput] = Field(min_length=1, max_length=10000)
    enable_llm: bool = True


class EvidenceMessage(BaseModel):
    channel_id: str
    channel_name: str
    message_ts: datetime
    thread_ts: str | None
    message_text: str


class CommunicationMetrics(BaseModel):
    recent_7d_message_count: int
    previous_7d_message_count: int
    activity_change_percent: float | None
    long_unanswered_count: int


class CommunicationRiskResponse(BaseModel):
    project_id: int
    project_name: str | None
    communication_risk_level: Literal["HIGH", "MEDIUM", "LOW"]
    reasons: list[str] = Field(min_length=1, max_length=3)
    evidence_messages: list[EvidenceMessage]
    recommended_action: str
    metrics: CommunicationMetrics
    analysis_window: dict[str, datetime]
    llm_status: Literal["SUCCEEDED", "SKIPPED_NO_API_KEY", "FALLBACK", "DISABLED"]
