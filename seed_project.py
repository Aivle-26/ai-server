import app.models

from app.core.database import SessionLocal
from app.models.project import Project


def main() -> None:
    db = SessionLocal()

    try:
        existing_project = (
            db.query(Project)
            .filter(Project.project_code == "PROJECT-001")
            .first()
        )

        if existing_project:
            print(
                f"프로젝트가 이미 존재합니다. "
                f"project_id={existing_project.project_id}"
            )
            return

        project = Project(
            project_name="AI Multi Agent 기반 IT 개발 프로젝트 관리 플랫폼",
            project_code="PROJECT-001",
            description="AI 기반 프로젝트 데이터 통합 및 관리 플랫폼",
            project_goal=(
                "프로젝트 계획, 보고서 생성, 리스크 탐지를 "
                "AI Multi Agent로 지원"
            ),
            status="PLANNING",
        )

        db.add(project)
        db.commit()
        db.refresh(project)

        print(f"프로젝트 생성 완료: project_id={project.project_id}")

    except Exception as error:
        db.rollback()
        print(f"프로젝트 생성 실패: {error}")

    finally:
        db.close()


if __name__ == "__main__":
    main()