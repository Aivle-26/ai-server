from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from .errors import ErrorResponse
from .handlers import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from .request_id import REQUEST_ID_HEADER, RequestIdMiddleware


DOCUMENTED_ERROR_STATUSES = (400, 413, 422, 502, 503, 504)


def install_http_contract(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
    _install_openapi_contract(app)


def _install_openapi_contract(app: FastAPI) -> None:
    original_openapi = app.openapi

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema

        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault(
            "schemas",
            {},
        )
        error_schema = ErrorResponse.model_json_schema(
            ref_template="#/components/schemas/{model}",
        )
        components.update(error_schema.pop("$defs", {}))
        components["ErrorResponse"] = error_schema

        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict) or "responses" not in operation:
                    continue
                for response in operation["responses"].values():
                    response.setdefault("headers", {})[REQUEST_ID_HEADER] = {
                        "description": "Request correlation identifier",
                        "schema": {"type": "string"},
                    }
                for status_code in DOCUMENTED_ERROR_STATUSES:
                    operation["responses"][str(status_code)] = {
                        "description": "Standard error response",
                        "headers": {
                            REQUEST_ID_HEADER: {
                                "description": "Request correlation identifier",
                                "schema": {"type": "string"},
                            }
                        },
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ErrorResponse"
                                }
                            }
                        },
                    }

        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
