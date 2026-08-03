import logging
from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .errors import (
    RETRYABLE_STATUSES,
    ErrorCode,
    ErrorResponse,
    error_code_for_status,
)
from .request_id import current_request_id


logger = logging.getLogger("uvicorn.error")


def _response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: list[dict[str, Any]] | dict[str, Any] | list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        request_id=current_request_id(),
        retryable=status_code in RETRYABLE_STATUSES,
        details=details,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = [
        {
            "type": error["type"],
            "location": list(error["loc"]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return _response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed.",
        details=details,
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    default_message = HTTPStatus(exc.status_code).phrase
    message = exc.detail if isinstance(exc.detail, str) else default_message
    details = None if isinstance(exc.detail, str) else exc.detail
    return _response(
        status_code=exc.status_code,
        code=error_code_for_status(exc.status_code),
        message=message,
        details=details,
        headers=exc.headers,
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "unhandled_request_error request_id=%s path=%s",
        current_request_id(),
        request.url.path,
    )
    return _response(
        status_code=500,
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="An unexpected server error occurred.",
    )
