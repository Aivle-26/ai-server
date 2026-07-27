from pathlib import Path

import fitz


class DocumentService:
    def extract_pdf_text(
        self,
        file_path: str
    ) -> dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"파일을 찾을 수 없습니다: {file_path}"
            )

        if path.suffix.lower() != ".pdf":
            raise ValueError(
                "현재는 PDF 파일만 처리할 수 있습니다."
            )

        document = fitz.open(file_path)

        pages = []
        full_text_parts = []

        try:
            for page_index, page in enumerate(document):
                page_text = page.get_text("text").strip()

                pages.append(
                    {
                        "page_number": page_index + 1,
                        "text": page_text,
                    }
                )

                if page_text:
                    full_text_parts.append(page_text)

        finally:
            document.close()

        full_text = "\n\n".join(full_text_parts)

        return {
            "file_name": path.name,
            "file_path": str(path),
            "file_extension": path.suffix.lower(),
            "page_count": len(pages),
            "text_content": full_text,
            "pages": pages,
            "character_count": len(full_text),
        }

    def split_text_into_chunks(
        self,
        text: str,
        chunk_size: int = 1500,
        overlap_size: int = 200,
    ) -> list[dict]:
        if chunk_size <= 0:
            raise ValueError(
                "chunk_size는 0보다 커야 합니다."
            )

        if overlap_size < 0:
            raise ValueError(
                "overlap_size는 0 이상이어야 합니다."
            )

        if overlap_size >= chunk_size:
            raise ValueError(
                "overlap_size는 chunk_size보다 작아야 합니다."
            )

        cleaned_text = text.strip()

        if not cleaned_text:
            return []

        chunks = []
        start_index = 0
        chunk_index = 0

        while start_index < len(cleaned_text):
            end_index = min(
                start_index + chunk_size,
                len(cleaned_text)
            )

            chunk_text = cleaned_text[
                start_index:end_index
            ].strip()

            if chunk_text:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_text": chunk_text,
                        "start_index": start_index,
                        "end_index": end_index,
                        "character_count": len(chunk_text),
                    }
                )

                chunk_index += 1

            if end_index >= len(cleaned_text):
                break

            start_index = end_index - overlap_size

        return chunks

    def process_pdf(
        self,
        file_path: str,
        chunk_size: int = 1500,
        overlap_size: int = 200,
    ) -> dict:
        document_data = self.extract_pdf_text(
            file_path=file_path
        )

        chunks = self.split_text_into_chunks(
            text=document_data["text_content"],
            chunk_size=chunk_size,
            overlap_size=overlap_size,
        )

        return {
            **document_data,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }