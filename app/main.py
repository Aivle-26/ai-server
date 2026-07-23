from fastapi import FastAPI

from app.api.risk_router import router as risk_router

app = FastAPI(
    title="AI Project Data Platform",
    version="0.1.0",
)

app.include_router(risk_router)


@app.get("/health")
def health():
    return {"status": "ok"}