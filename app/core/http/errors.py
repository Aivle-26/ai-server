from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ErrorCode(StrEnum):
    BAD_REQUEST = "BAD_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AI_UPSTREAM_ERROR = "AI_UPSTREAM_ERROR"
    AI_SERVICE_UNAVAILABLE = "AI_SERVICE_UNAVAILABLE"
    AI_TIMEOUT = "AI_TIMEOUT"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    HTTP_ERROR = "HTTP_ERROR"


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str
    request_id: str
    retryable: bool = False
    details: list[dict[str, Any]] | dict[str, Any] | list[Any] | None = None


ERROR_CODE_BY_STATUS = {
    400: ErrorCode.BAD_REQUEST,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.VALIDATION_ERROR,
    502: ErrorCode.AI_UPSTREAM_ERROR,
    503: ErrorCode.AI_SERVICE_UNAVAILABLE,
    504: ErrorCode.AI_TIMEOUT,
}

RETRYABLE_STATUSES = {429, 502, 503, 504}


def error_code_for_status(status_code: int) -> ErrorCode:
    if status_code >= 500:
        return ERROR_CODE_BY_STATUS.get(
            status_code,
            ErrorCode.INTERNAL_SERVER_ERROR,
        )
    return ERROR_CODE_BY_STATUS.get(status_code, ErrorCode.HTTP_ERROR)
