from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()

PLANNING_ANALYSIS_TIMEOUT_ENV = "PLANNING_ANALYSIS_TIMEOUT_SECONDS"
PLANNING_MAX_ANALYSIS_CHUNKS_ENV = "PLANNING_MAX_ANALYSIS_CHUNKS"
PLANNING_READJUST_MAX_ANALYSIS_CHUNKS_ENV = (
    "PLANNING_READJUST_MAX_ANALYSIS_CHUNKS"
)
PLANNING_ANALYSIS_RETRY_COUNT_ENV = "PLANNING_ANALYSIS_RETRY_COUNT"


@dataclass(frozen=True)
class PlanningAnalysisSettings:
    planning_analysis_timeout_seconds: int = 300
    planning_max_analysis_chunks: int = 2
    planning_readjust_max_analysis_chunks: int = 4
    planning_analysis_retry_count: int = 0

    def __post_init__(self) -> None:
        if self.planning_analysis_timeout_seconds <= 0:
            raise ValueError(
                "planning_analysis_timeout_seconds must be positive"
            )
        if self.planning_max_analysis_chunks <= 0:
            raise ValueError(
                "planning_max_analysis_chunks must be positive"
            )
        if self.planning_readjust_max_analysis_chunks <= 0:
            raise ValueError(
                "planning_readjust_max_analysis_chunks must be positive"
            )
        if self.planning_analysis_retry_count != 0:
            raise ValueError(
                "planning_analysis_retry_count must be zero while retries "
                "are disabled"
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
            planning_readjust_max_analysis_chunks=_read_int(
                PLANNING_READJUST_MAX_ANALYSIS_CHUNKS_ENV,
                cls.planning_readjust_max_analysis_chunks,
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
