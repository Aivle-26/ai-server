from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# SQLite 데이터베이스 경로
DATABASE_URL = "sqlite:///./data/project.db"

# 데이터베이스 엔진 생성
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# 세션 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# 모든 모델이 상속받는 Base 클래스
class Base(DeclarativeBase):
    pass


# DB 세션 가져오기
def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()