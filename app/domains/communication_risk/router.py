from datetime import datetime, timezone

from fastapi import APIRouter

from .graph import CommunicationRiskGraph
from .schemas import CommunicationRiskRequest, CommunicationRiskResponse

router = APIRouter()
communication_risk_graph = CommunicationRiskGraph()


@router.post(
    "/api/v1/risk/communication/analyze",
    response_model=CommunicationRiskResponse,
    summary="프로젝트 커뮤니케이션 위험 분석",
    description="프로젝트의 Slack 메시지를 분석하여 커뮤니케이션 위험도와 판단 근거를 반환합니다.",
)
def analyze_communication_risk(
    request: CommunicationRiskRequest,
) -> dict:
    analysis_end = request.analysis_end or datetime.now(timezone.utc)
    payload = request.model_dump(mode="json")
    payload["analysis_end"] = analysis_end.isoformat()
    return communication_risk_graph.invoke(payload)
