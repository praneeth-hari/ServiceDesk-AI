import contextvars
import logging
import re
import time
import uuid
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable holding the active request ID for the current async task
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# Regex pattern for a sane X-Request-ID: max 64 chars, alphanumeric + dashes only
SANE_REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def get_sane_request_id(incoming_id: Optional[str]) -> str:
    """
    Validate incoming X-Request-ID header.
    If present and sane (1-64 characters of letters, digits, and dashes), return it.
    Otherwise, generate a fresh UUID4.
    """
    if incoming_id and SANE_REQUEST_ID_REGEX.fullmatch(incoming_id.strip()):
        return incoming_id.strip()
    return str(uuid.uuid4())


class RequestIDFilter(logging.Filter):
    """
    Standard library logging Filter that injects the current request_id
    from contextvars into every LogRecord as record.request_id.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure application logging using the standard library.
    Sets the log level from settings and attaches RequestIDFilter to inject request_id.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logger = logging.getLogger("helpdesk_api")
    logger.setLevel(numeric_level)

    # Attach RequestIDFilter directly to the logger so all handlers and caplog see record.request_id
    if not any(isinstance(f, RequestIDFilter) for f in logger.filters):
        logger.addFilter(RequestIDFilter())

    # Configure standard stream handler if no handlers are configured yet
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.addFilter(RequestIDFilter())
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [request_id=%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False


class RequestIDLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Extracts or generates a sane request ID.
    2. Stores it in contextvars for the duration of the request.
    3. Adds X-Request-ID header to the HTTP response.
    4. Logs one line per request: request_id, method, path, status_code, and duration_ms.
    Never logs passwords, tokens, Authorization headers, or request bodies.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        raw_req_id = request.headers.get("X-Request-ID")
        request_id = get_sane_request_id(raw_req_id)

        token = request_id_ctx.set(request_id)
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger = logging.getLogger("helpdesk_api")
            logger.info(
                "request_id=%s method=%s path=%s status_code=%d duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )
            request_id_ctx.reset(token)
