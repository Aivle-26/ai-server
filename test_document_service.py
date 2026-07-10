from pprint import pprint

from app.services.document_service import DocumentService


def main() -> None:
    service = DocumentService()

    try:
        result = service.process_pdf(
            file_path="sample_data/sample_rfp.pdf",
            chunk_size=1000,
            overlap_size=150,
        )

        print("=== PDF 처리 결과 ===")
        print("파일명:", result["file_name"])
        print("페이지 수:", result["page_count"])
        print("전체 글자 수:", result["character_count"])
        print("Chunk 수:", result["chunk_count"])

        print("\n=== 첫 번째 Chunk ===")

        if result["chunks"]:
            pprint(result["chunks"][0])
        else:
            print("추출된 텍스트가 없습니다.")

    except Exception as error:
        print("=== PDF 처리 실패 ===")
        print(error)


if __name__ == "__main__":
    main()