from fastapi import FastAPI

from app.core.http import install_http_contract

from app.domains.communication_risk.router import (
    router as communication_risk_router,
)
from app.domains.planning_costs.router import router as planning_costs_router
from app.domains.planning_documents.router import (
    router as planning_documents_router,
)
from app.domains.planning_resources.router import (
    router as planning_resources_router,
)
from app.domains.planning_resources.ui_mockup_router import (
    router as ui_mockup_router,
)
from app.domains.planning_schedule.router import (
    router as planning_schedule_router,
)
from app.domains.planning_wbs.router import router as planning_wbs_router
from app.domains.project_risk.router import router as project_risk_router
from app.domains.reporting.router import router as reporting_router


app = FastAPI(
    title="AI Project Data Platform",
    version="0.1.0",
)

app.include_router(project_risk_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(communication_risk_router)
app.include_router(planning_documents_router)
app.include_router(planning_wbs_router)
app.include_router(planning_schedule_router)
app.include_router(planning_resources_router)
app.include_router(ui_mockup_router)
app.include_router(planning_costs_router)
app.include_router(reporting_router)

install_http_contract(app)

