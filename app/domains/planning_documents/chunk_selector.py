from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


RELEVANCE_KEYWORDS = (
    "요구사항",
    "기능",
    "구현",
    "시스템",
    "개발",
    "제공",
    "지원",
    "연동",
    "필수",
    "조건",
    "검수",
    "납품",
    "산출물",
    "보안",
    "개인정보",
    "성능",
    "일정",
    "사용자",
    "관리자",
    "shall",
    "must",
    "required",
    "requirement",
)


@dataclass(frozen=True)
class AnalysisCandidate:
    kind: Literal["TEXT", "PDF_VISION"]
    source_document: str
    document_order: int
    chunk_index: int
    original_order: int
    payload_index: int
    relevance_score: int


@dataclass(frozen=True)
class AnalysisSelection:
    chunk_indices: tuple[int, ...]
    vision_document_indices: tuple[int, ...]
    candidates: tuple[AnalysisCandidate, ...]

    @property
    def count(self) -> int:
        return len(self.candidates)


def select_analysis_inputs(
    *,
    chunks: list[dict[str, Any]],
    vision_documents: list[Any],
    document_names: list[str],
    max_analysis_chunks: int,
) -> AnalysisSelection:
    if max_analysis_chunks < 1:
        raise ValueError("max_analysis_chunks must be positive")

    document_order: dict[str, int] = {}
    for index, name in enumerate(document_names):
        document_order.setdefault(name, index)
    candidates: list[AnalysisCandidate] = []

    for index, chunk in enumerate(chunks):
        source_document = str(chunk["source_document"])
        candidates.append(AnalysisCandidate(
            kind="TEXT",
            source_document=source_document,
            document_order=document_order.get(
                source_document,
                len(document_names),
            ),
            chunk_index=int(chunk["chunk_index"]),
            original_order=index,
            payload_index=index,
            relevance_score=_relevance_score(str(chunk["text"])),
        ))

    vision_offset = len(candidates)
    for index, document in enumerate(vision_documents):
        source_document = str(document.file_name)
        candidates.append(AnalysisCandidate(
            kind="PDF_VISION",
            source_document=source_document,
            document_order=document_order.get(
                source_document,
                len(document_names) + index,
            ),
            chunk_index=1,
            original_order=vision_offset + index,
            payload_index=index,
            relevance_score=0,
        ))

    if len(candidates) <= max_analysis_chunks:
        selected = candidates
    else:
        ranked = sorted(candidates, key=_ranking_key)
        selected = _select_with_document_fairness(
            ranked,
            max_analysis_chunks,
        )

    selected = sorted(selected, key=_source_order_key)
    return AnalysisSelection(
        chunk_indices=tuple(
            candidate.payload_index
            for candidate in selected
            if candidate.kind == "TEXT"
        ),
        vision_document_indices=tuple(
            candidate.payload_index
            for candidate in selected
            if candidate.kind == "PDF_VISION"
        ),
        candidates=tuple(selected),
    )


def _relevance_score(text: str) -> int:
    normalized = text.casefold()
    return sum(
        normalized.count(keyword.casefold())
        for keyword in RELEVANCE_KEYWORDS
    )


def _ranking_key(
    candidate: AnalysisCandidate,
) -> tuple[int, int, int, int]:
    return (
        -candidate.relevance_score,
        candidate.document_order,
        candidate.chunk_index,
        candidate.original_order,
    )


def _source_order_key(
    candidate: AnalysisCandidate,
) -> tuple[int, int, int]:
    return (
        candidate.document_order,
        candidate.chunk_index,
        candidate.original_order,
    )


def _select_with_document_fairness(
    ranked: list[AnalysisCandidate],
    limit: int,
) -> list[AnalysisCandidate]:
    selected: list[AnalysisCandidate] = []
    represented_documents: set[tuple[int, str]] = set()
    distinct_documents = {
        (candidate.document_order, candidate.source_document)
        for candidate in ranked
    }

    if limit > 1 and len(distinct_documents) > 1:
        for candidate in ranked:
            document_key = (
                candidate.document_order,
                candidate.source_document,
            )
            if document_key in represented_documents:
                continue
            selected.append(candidate)
            represented_documents.add(document_key)
            if len(selected) == min(limit, len(distinct_documents)):
                break

    for candidate in ranked:
        if len(selected) == limit:
            break
        if candidate not in selected:
            selected.append(candidate)
    return selected
