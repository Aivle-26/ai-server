import unittest
from types import SimpleNamespace

from app.domains.planning_documents.chunk_selector import (
    select_analysis_inputs,
)


def chunk(document: str, index: int, text: str) -> dict[str, object]:
    return {
        "source_document": document,
        "chunk_index": index,
        "text": text,
    }


class PlanningAnalysisChunkSelectorTest(unittest.TestCase):
    def test_all_inputs_are_selected_when_count_is_at_most_limit(self):
        selection = select_analysis_inputs(
            chunks=[
                chunk("one.txt", 1, "overview"),
                chunk("one.txt", 2, "requirements"),
            ],
            vision_documents=[],
            document_names=["one.txt"],
            max_analysis_chunks=2,
        )

        self.assertEqual(selection.chunk_indices, (0, 1))
        self.assertEqual(selection.vision_document_indices, ())

    def test_relevance_selection_is_not_a_first_two_slice(self):
        selection = select_analysis_inputs(
            chunks=[
                chunk("one.txt", 1, "general introduction"),
                chunk("one.txt", 2, "company history"),
                chunk(
                    "one.txt",
                    3,
                    "The system must implement required security.",
                ),
            ],
            vision_documents=[],
            document_names=["one.txt"],
            max_analysis_chunks=2,
        )

        self.assertEqual(selection.chunk_indices, (0, 2))

    def test_multiple_documents_receive_representation_when_possible(self):
        selection = select_analysis_inputs(
            chunks=[
                chunk(
                    "requirements.txt",
                    1,
                    "must required requirement system security",
                ),
                chunk(
                    "requirements.txt",
                    2,
                    "must required requirement feature",
                ),
                chunk("contract.txt", 1, "delivery condition"),
            ],
            vision_documents=[],
            document_names=["requirements.txt", "contract.txt"],
            max_analysis_chunks=2,
        )

        selected_documents = {
            candidate.source_document
            for candidate in selection.candidates
        }
        self.assertEqual(
            selected_documents,
            {"requirements.txt", "contract.txt"},
        )

    def test_selection_is_deterministic_and_preserves_source_order(self):
        arguments = {
            "chunks": [
                chunk("one.txt", 1, "must support users"),
                chunk("one.txt", 2, "required security"),
                chunk("two.txt", 1, "shall provide integration"),
            ],
            "vision_documents": [],
            "document_names": ["one.txt", "two.txt"],
            "max_analysis_chunks": 2,
        }

        first = select_analysis_inputs(**arguments)
        second = select_analysis_inputs(**arguments)

        self.assertEqual(first, second)
        self.assertEqual(
            [
                candidate.document_order
                for candidate in first.candidates
            ],
            sorted(
                candidate.document_order
                for candidate in first.candidates
            ),
        )

    def test_text_and_pdf_vision_share_the_same_call_budget(self):
        selection = select_analysis_inputs(
            chunks=[
                chunk("one.txt", 1, "must provide security"),
                chunk("one.txt", 2, "general notes"),
            ],
            vision_documents=[
                SimpleNamespace(file_name="scan.pdf"),
            ],
            document_names=["one.txt", "scan.pdf"],
            max_analysis_chunks=2,
        )

        self.assertEqual(selection.count, 2)
        self.assertEqual(selection.vision_document_indices, (0,))


if __name__ == "__main__":
    unittest.main()
