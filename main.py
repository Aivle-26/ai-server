from fastapi import FastAPI


app = FastAPI(
    title="AI Server",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "ok"}
