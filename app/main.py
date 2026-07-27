from fastapi import FastAPI

from app.api.communication_risk_router import router as communication_risk_router
from app.api.risk_router import router as risk_router

app = FastAPI(
    title="AI Project Data Platform",
    version="0.1.0",
)

app.include_router(risk_router)
app.include_router(communication_risk_router)


@app.get("/health")
def health():
    return {"status": "ok"}