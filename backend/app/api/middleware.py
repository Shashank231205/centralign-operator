"""Request-scoped concerns: correlation IDs, access timing and the uniform error envelope."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.schemas.common import ErrorBody, ErrorEnvelope
from app.core.errors import AppError, RateLimitedError
from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def _envelope(
    status_code: int, body: ErrorBody, headers: Mapping[str, str] | None = None
) -> Response:
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(error=body).model_dump(),
        headers=headers,
    )


async def _handle_app_error(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, AppError)
    headers = None
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(max(1, round(exc.retry_after_seconds)))}
    if exc.status_code >= 500:
        logger.error("request failed", extra={"code": exc.code, "error": exc.message})
    return _envelope(
        exc.status_code, ErrorBody(code=exc.code, message=exc.message, details=exc.details), headers
    )


async def _handle_validation_error(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    return _envelope(
        422,
        ErrorBody(
            code="validation_error",
            message="Request validation failed",
            details={"errors": exc.errors()},
        ),
    )


async def _handle_http_error(_: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return _envelope(exc.status_code, ErrorBody(code=code, message=str(exc.detail)), exc.headers)


async def _handle_unexpected(_: Request, exc: Exception) -> Response:
    logger.exception("unhandled error", exc_info=exc)
    return _envelope(500, ErrorBody(code="internal_error", message="Internal server error"))


async def _correlate_and_time(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return response


def install_middleware(app: FastAPI) -> None:
    app.middleware("http")(_correlate_and_time)
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected)
