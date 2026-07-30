from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()

PLANNING_ANALYSIS_TIMEOUT_ENV = "PLANNING_ANALYSIS_TIMEOUT_SECONDS"
PLANNING_MAX_ANALYSIS_CHUNKS_ENV = "PLANNING_MAX_ANALYSIS_CHUNKS"
PLANNING_ANALYSIS_RETRY_COUNT_ENV = "PLANNING_ANALYSIS_RETRY_COUNT"


@dataclass(frozen=True)
class PlanningAnalysisSettings:
    planning_analysis_timeout_seconds: int = 180
    planning_max_analysis_chunks: int = 2
    planning_analysis_retry_count: int = 0

    def __post_init__(self) -> None:
        if self.planning_analysis_timeout_seconds <= 1:
            raise ValueError(
                "planning_analysis_timeout_seconds must be greater than 1"
            )
        if self.planning_max_analysis_chunks <= 1:
            raise ValueError(
                "planning_max_analysis_chunks must be greater than 1"
            )
        if self.planning_analysis_retry_count < 0:
            raise ValueError(
                "planning_analysis_retry_count must be zero or greater"
            )
        if self.planning_analysis_retry_count != 0:
            raise ValueError(
                "planning_analysis_retry_count must be zero while "
                "analysis retries are disabled"
            )

    @classmethod
    def from_env(cls) -> PlanningAnalysisSettings:
        return cls(
            planning_analysis_timeout_seconds=_read_int(
                PLANNING_ANALYSIS_TIMEOUT_ENV,
                cls.planning_analysis_timeout_seconds,
            ),
            planning_max_analysis_chunks=_read_int(
                PLANNING_MAX_ANALYSIS_CHUNKS_ENV,
                cls.planning_max_analysis_chunks,
            ),
            planning_analysis_retry_count=_read_int(
                PLANNING_ANALYSIS_RETRY_COUNT_ENV,
                cls.planning_analysis_retry_count,
            ),
        )


def _read_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
