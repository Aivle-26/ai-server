from datetime import datetime, timezone

from fastapi import FastAPI

from app.agents.communication_risk_graph import CommunicationRiskGraph
from app.schemas.communication_risk import (
    CommunicationRiskRequest,
    CommunicationRiskResponse,
)


app = FastAPI(
    title="AI Project Management Server",
    version="0.1.0",
)

communication_risk_graph = CommunicationRiskGraph()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/risk/communication/analyze",
    response_model=CommunicationRiskResponse,
    summary="Analyze project Slack communication risk",
)
def analyze_communication_risk(
    request: CommunicationRiskRequest,
) -> dict:
    analysis_end = request.analysis_end or datetime.now(timezone.utc)
    payload = request.model_dump(mode="json")
    payload["analysis_end"] = analysis_end.isoformat()
    return communication_risk_graph.invoke(payload)
