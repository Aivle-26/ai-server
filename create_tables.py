from app.core.database import Base, engine
from app.models.project import Project
from app.models.external_data import ExternalRawData
from app.models.normalized_event import NormalizedEvent
from app.models.requirement import Requirement
from app.models.wbs import WBS
from app.models.member import Member, MemberSkill, MemberWorkload
from app.models.schedule import Schedule
from app.models.risk import Risk


def create_tables():
    Base.metadata.create_all(bind=engine)
    print("테이블 생성 완료")


if __name__ == "__main__":
    create_tables()