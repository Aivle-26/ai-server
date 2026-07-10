from pprint import pprint

import app.models

from app.core.database import SessionLocal
from app.services.context_builder import ContextBuilder


def main() -> None:
    db = SessionLocal()
    builder = ContextBuilder()

    try:
        context = builder.build_common_context(
            db=db,
            project_id=1,
        )

        print("=== AI 입력 Context ===")
        pprint(context)

    except Exception as error:
        print("=== Context 생성 실패 ===")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()