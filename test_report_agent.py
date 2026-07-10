from pprint import pprint

import app.models

from app.agents.report_agent import ReportAgent
from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder


db = SessionLocal()

builder = ContextBuilder()

agent = ReportAgent()

context = builder.build_report_context(
    db=db,
    project_id=1,
)

result = agent.generate(context)

print("===== Report =====")

pprint(result)

db.close()