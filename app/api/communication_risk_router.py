"""Slack 커뮤니케이션 리스크 분석 엔드포인트.

백엔드(Spring)의 HttpCommunicationRiskAgentClient가 호출하는 주소:
    POST /api/v1/risk/communication/analyze

이 서버는 Slack에 직접 접속하지 않는 무상태 분석기다.
메시지 수집·프로젝트 매핑·결과 저장은 전부 백엔드 책임이고,
여기서는 넘겨받은 messages[]로 CommunicationRiskGraph를 돌려
CommunicationRiskResponse를 돌려준다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from app.agents.communication_risk_graph import CommunicationRiskGraph
from app.schemas.communication_risk import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
)

router = APIRouter(
    prefix="/api/v1/risk/communication",
    tags=["Communication Risk"],
)

# StateGraph 컴파일 비용이 있어 요청마다 만들지 않고 모듈 로드 시 1회만 만든다.
_graph = CommunicationRiskGraph()


@router.post(
    "/analyze",
    response_model=CommunicationRiskResponse,
    summary="Slack 커뮤니케이션 리스크 분석",
)
def analyze_communication_risk(
    request: CommunicationRiskRequest,
) -> CommunicationRiskResponse:
    # analysis_end가 없으면 지금 시각 기준으로 최근/이전 7일을 나눈다.
    analysis_end = request.analysis_end or datetime.now()

    result = _graph.invoke(
        {
            "project_id": request.project_id,
            "project_name": request.project_name,
            "analysis_end": analysis_end.isoformat(),
            "messages": [
                message.model_dump(mode="json")
                for message in request.messages
            ],
            "enable_llm": request.enable_llm,
        }
    )

    return CommunicationRiskResponse(**result)
